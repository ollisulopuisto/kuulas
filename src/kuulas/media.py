"""Imported audio, stored once as FLAC at the project rate.

**Identity is the content, never the name.** A media id is the SHA-256 of
the file's bytes, so a file that was renamed, moved or copied is the same
media; ``media_paths`` remembers every path each hash has been seen under.

**Storage.** Each source becomes one FLAC working file at the project rate:

* Integer PCM already at the project rate is written at its own bit depth
  and checked sample by sample against the source. When it matches, the
  FLAC *is* the original and no other copy is kept.
* Anything else (resampled, float, lossy) becomes 24-bit FLAC, and the
  original file is kept beside it in ``originals/``.

A project folder is complete on its own: moving or deleting the source
cannot break it.

**Metadata** is a ``media`` row in ``project.sqlite`` (docs/FORMAT.md). The
row is inserted only after the file is complete and renamed, so the row is
the "import finished" marker: a crash mid-import leaves nothing that looks
done. Rows are updated column by column, never replaced, so columns a newer
kuulas added survive. Waveform peaks are a cache (``caches/peaks/``), keyed
by content and rebuilt when missing.

**Fail soft (WP34).** A bad file costs that file, never the batch or the
session. Every source is probed first (``probe``, with a timeout), so an
empty file, a garbage header or a video without audio is refused with a
message that says so before anything is decoded. A file that decodes only
as far as some point (truncated, damaged in the middle) comes in as far as
it goes and is *marked partial* (``Media.extra["partial"]``), with a
warning. External decoders are killed when they stall (``STALL_SEC``).
Free space is checked before decoding and a full disk or a vanished source
drive removes the half-written file and says which. ``import_batch``
reports each file's outcome as an ``ImportResult``.

**Reading.** The mixer asks for arbitrary slices on the audio thread, so
reads go through a cache of decoded chunks; FLAC seeks are sample-exact.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import os
import platform
import shutil
import struct
import subprocess
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePath

import numpy as np
import soundfile as sf
from speechmix.binaries import get_binary_path

from . import caches, levels
from . import db as dbm
from . import peaks as peak_pyramid
from .clock import RateError, check_rate, frames_to_flicks
from .memory import BUDGET, MemoryBudget
from .messages import KuulasError, t
from .model import Media

log = logging.getLogger("kuulas.media")

#: Frames per peak at the finest zoom level the UI asks for.
PEAK_FRAMES = 256
#: The peaks algorithm, for cache keys: bump when ``_peaks`` changes.
PEAKS_ALGORITHM = "peaks@1"
#: Decode/encode step, and the unit of the read cache.
CHUNK_SEC = 10
#: Decoded chunks kept in memory: 48 x 10 s of stereo float32 at 48 kHz
#: is about 180 MB, enough for every track of a session around the playhead.
CACHE_CHUNKS = 48
#: Source sample formats FLAC holds without loss (libsndfile subtypes).
PCM_SUBTYPES = {"PCM_16", "PCM_24"}
#: libsndfile subtypes whose frame count is exact and whose header can be
#: trusted for "how long should this be"; anything else (MP3, Ogg, ...) is
#: probed with ffprobe, which estimates.
EXACT_SUBTYPE_PREFIXES = ("PCM", "FLOAT", "DOUBLE")
#: How long ffprobe may take. It reads headers only, so a healthy file
#: answers in milliseconds; this is for a file on a stalled network share.
PROBE_TIMEOUT_SEC = 20.0
#: An ffmpeg that has delivered nothing for this long is hung and is killed.
#: Decoding runs far faster than real time, so 10 s of audio never takes
#: anywhere near this; a slow network drive may.
STALL_SEC = 120.0
#: A BWF TimeReference is "samples since midnight". More than a day is a
#: recorder with a broken clock or a damaged header, not a start time.
MAX_TIME_REFERENCE_HOURS = 24
#: Bytes per sample the free-space estimate assumes for the working FLAC:
#: 24-bit, uncompressed. FLAC of noisy audio comes close to that, and the
#: size of the real file is not known before it is encoded.
ESTIMATE_BYTES_PER_SAMPLE = 3
#: A decode that comes up short of what the file promised by more than this
#: is partial (the larger of the two applies).
SHORTFALL_SEC = 0.25
SHORTFALL_FRACTION = 0.01
#: errno values that mean "the drive under the file went away" (a source
#: that no longer exists counts too, whatever the errno).
VANISHED_ERRNOS = frozenset(
    getattr(errno, name) for name in
    ("EIO", "ENXIO", "ENODEV", "ESTALE", "ENOTCONN", "EHOSTDOWN", "ETIMEDOUT")
    if hasattr(errno, name))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _walk_wav(f) -> Iterator[tuple[bytes, int, int]]:
    """``(chunk id, size, body position)`` for each chunk of a RIFF/RF64 WAV.

    RF64 keeps the sizes that do not fit 32 bits in a ``ds64`` chunk and
    writes 0xFFFFFFFF in the chunk itself; the real size is used here, so a
    chunk after a multi-gigabyte ``data`` chunk is still found. The caller may
    read the body; the walk seeks to the next chunk by itself.
    """
    head = f.read(12)
    if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
        return
    big: dict[bytes, int] = {}
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            return
        cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
        pos = f.tell()
        if cid == b"ds64":
            raw = f.read(min(size, 28))
            if len(raw) >= 16:
                big[b"data"] = struct.unpack_from("<Q", raw, 8)[0]
        elif size == 0xFFFFFFFF and cid in big:
            size = big[cid]
        yield cid, size, pos
        f.seek(pos + size + size % 2)


def wav_header(path: Path) -> dict:
    """What a WAV's headers say, whatever its audio really holds: ``rate``,
    ``time_reference`` (BWF samples), and ``frames``, the length the ``data``
    chunk promises. A truncated file promises more than it has, which is how
    a partial import knows how much is missing. Absent keys: not known."""
    out: dict = {}
    block_align = 0
    try:
        with path.open("rb") as f:
            for cid, size, pos in _walk_wav(f):
                if cid == b"fmt " and size >= 16:
                    fmt = f.read(16)
                    out["rate"] = struct.unpack_from("<I", fmt, 4)[0]
                    block_align = struct.unpack_from("<H", fmt, 12)[0]
                elif cid == b"bext" and size >= 346:
                    f.seek(pos + 338)
                    out["time_reference"] = struct.unpack("<Q", f.read(8))[0]
                elif cid == b"data" and block_align and 0 < size < 0xFFFFFFFF:
                    # 0 and 0xFFFFFFFF are what streaming writers leave behind.
                    out["frames"] = size // block_align
    except (OSError, struct.error):
        pass
    return out


def bwf_time_reference(path: Path) -> tuple[int, int] | None:
    """``(TimeReference samples, file rate)`` from a WAV's ``bext`` chunk, if any.

    Field recorders write the recording's start (samples since midnight)
    there; it is how files from one shoot line up without listening.
    """
    head = wav_header(path)
    if "time_reference" in head and head.get("rate"):
        return head["time_reference"], head["rate"]
    return None


def drive_of(path: PurePath) -> str:
    """The name of the drive a path lives on, for "ZOOM H6 was unplugged".

    ``/Volumes/<name>`` (macOS), ``/media/<user>/<name>`` and
    ``/run/media/<user>/<name>`` (Linux desktops), ``/mnt/<name>``, a
    Windows drive letter; anything else is the internal disk, ``/``.
    """
    if path.drive:
        return path.drive
    parts = path.parts
    if len(parts) > 3 and parts[1] in ("Volumes", "mnt"):
        return parts[2]
    if len(parts) > 4 and parts[1] == "media":
        return parts[3]
    if len(parts) > 5 and parts[1:3] == ("run", "media"):
        return parts[4]
    return path.anchor or "/"


def workers() -> int:
    """Parallel jobs for imports and analysis: every core but one for the UI."""
    return max(1, (os.cpu_count() or 2) - 1)


#: Columns an import or a consolidation sets; the rest of a row (name, time
#: reference, tags, extra, unknown columns) is never touched by them.
_FILE_COLUMNS = ("storage", "channels", "source_rate", "source_frames", "subtype",
                 "lossless", "linked_path", "linked_size", "linked_mtime_ns",
                 "linked_package_rel", "linked_series_rel")


def _preferences_path() -> Path:
    if os.environ.get("XDG_CONFIG_HOME"):
        base = Path(os.environ["XDG_CONFIG_HOME"])
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path.home() / ".config"
    return base / "kuulas" / "media.json"


def _relative(path: Path, root: Path | None) -> str | None:
    if root is None:
        return None
    try:
        return Path(os.path.relpath(path, root)).as_posix()
    except ValueError:
        return None


@dataclass
class Note:
    """A warning about an import that succeeded: a catalog key and its values."""

    key: str
    params: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return t(self.key, **self.params)


@dataclass
class ImportResult:
    """What became of one file in a batch: its ``media`` or its ``error``,
    and the ``warnings`` (``Note``) either way."""

    path: Path
    media: Media | None = None
    error: Exception | None = None
    warnings: list[Note] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class Probe:
    """What a file says about itself before anything is decoded.

    ``seconds`` is how long it claims to be (None if unknown); ``exact`` is
    true when that claim is a count from the header (WAV, FLAC), false when it
    is an estimate (VBR MP3), which decides whether a shortfall means damage.
    """

    channels: int
    seconds: float | None
    exact: bool

    def frames(self, rate: int) -> int | None:
        return None if self.seconds is None else round(self.seconds * rate)


@dataclass
class _Job:
    """One import in flight: where its warnings go and what it was probed as."""

    path: Path
    notes: list[Note]
    probe: Probe
    needed: int = 0


def _exists(path: Path) -> bool:
    try:
        path.stat()
    except OSError:
        return False
    return True


def _mb(n: int) -> int:
    return round(n / 1_000_000)


def _clock(frames: int, rate: int) -> str:
    """``41:03`` or ``1:02:03``: how a partial import says how far it got."""
    seconds = int(frames / rate)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def probe(path: Path) -> Probe:
    """Look at ``path`` without decoding it; raises ``MediaError`` for a file
    that is empty, unreadable or has no audio. ffprobe runs under a timeout."""
    name = path.name
    if path.stat().st_size == 0:
        raise MediaError("error.media.empty", name=name)
    try:
        info = sf.info(str(path))
    except (sf.LibsndfileError, RuntimeError):
        info = None
    if info is not None and info.subtype.startswith(EXACT_SUBTYPE_PREFIXES):
        # A truncated WAV reports the frames that are there; its header still
        # says how many there should have been.
        promised = max(info.frames, wav_header(path).get("frames", 0))
        if promised == 0:
            with sf.SoundFile(str(path)) as f:  # a streamed FLAC leaves its count 0
                if len(f.read(1)) == 0:
                    raise MediaError("error.media.empty", name=name)
            return Probe(info.channels, None, False)
        return Probe(info.channels, promised / info.samplerate, True)
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [get_binary_path("ffprobe"), "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=channels:format=duration", "-of", "json",
             str(path)],
            capture_output=True, text=True, errors="replace", check=False,
            stdin=subprocess.DEVNULL, timeout=PROBE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        raise MediaError("error.media.probe_timeout", name=name,
                         seconds=round(PROBE_TIMEOUT_SEC)) from None
    if out.returncode != 0:
        lines = out.stderr.strip().splitlines()
        raise MediaError("error.media.unreadable", name=name,
                         error=lines[-1] if lines else "")
    try:
        found = json.loads(out.stdout)
    except ValueError:
        raise MediaError("error.media.unreadable", name=name, error="") from None
    streams = found.get("streams") or []
    if not streams:
        raise MediaError("error.media.no_audio", name=name)
    channels = int(streams[0].get("channels") or 0)
    if channels < 1:
        raise MediaError("error.media.unreadable", name=name, error="")
    try:
        seconds = float(found.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        seconds = None  # ffprobe says "N/A" for streams it cannot measure
    return Probe(channels, seconds, False)


class MediaStore:
    """``folder`` is the package's ``media/``. The database and ``caches/``
    default to its siblings, as in a package (docs/FORMAT.md, "Layout")."""

    def __init__(self, folder: str | Path, rate: int, *, db: str | Path | None = None,
                 cache_root: str | Path | None = None, read_only: bool = False,
                 budget: MemoryBudget | None = None,
                 package_root: str | Path | None = None,
                 series_root: str | Path | None = None,
                 preferences: str | Path | None = None):
        self.budget = BUDGET if budget is None else budget
        self.folder = Path(folder)
        self.package_root = Path(package_root) if package_root else self.folder.parent
        self.series_root = Path(series_root) if series_root else None
        self.preferences = Path(preferences) if preferences else _preferences_path()
        self._resolved_paths: dict[str, str] = {}
        self._resolution_done = threading.Event()
        self._resolution_stop = threading.Event()
        self._resolution_thread: threading.Thread | None = None
        self._load_preferences()
        self.read_only = read_only
        if not read_only:
            self.folder.mkdir(parents=True, exist_ok=True)
        check_rate(rate)
        self.rate = rate
        self.cache_root = (Path(cache_root) if cache_root
                           else self.folder.parent / "caches")
        self.db = dbm.connect(Path(db) if db else self.folder.parent / "project.sqlite",
                              read_only=read_only)
        if not read_only:
            dbm.ensure_schema(self.db, rate)
        self._lock = threading.Lock()
        self._db_lock = threading.RLock()
        #: One lock per media id, held while a file is imported: two cores
        #: meeting the same bytes (a batch that lists a file twice) must not
        #: both encode it. The second waits, then finds the finished row.
        self._import_locks: dict[str, threading.Lock] = {}
        self._handles: dict[str, tuple[threading.Lock, sf.SoundFile]] = {}
        self._cache: OrderedDict[tuple[str, int], np.ndarray] = OrderedDict()
        self._meta: dict[str, dict] = {}
        #: Is each linked file still there and unchanged? Checked (stat and,
        #: if the mtime moved, a re-hash) here, in ``missing`` and in
        #: ``relink``, never in ``read``: that runs on the audio thread.
        self._linked_ok: dict[str, bool] = {}
        self.missing()
        self._resolution_thread = threading.Thread(
            target=self._resolve_missing, name="kuulas-media-resolver", daemon=True)
        self._resolution_thread.start()

    def close(self) -> None:
        self._resolution_stop.set()
        if self._resolution_thread is not None:
            self._resolution_thread.join(timeout=5)
        with self._lock:
            for _, f in self._handles.values():
                f.close()
            self._handles.clear()
        self.db.close()

    def _load_preferences(self) -> None:
        try:
            data = json.loads(self.preferences.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self._media_folders = [Path(p) for p in data.get("media_folders", [])]
        self._rewrites = list(data.get("path_rewrites", []))

    def _save_preferences(self) -> None:
        if self.read_only:
            return
        self.preferences.parent.mkdir(parents=True, exist_ok=True)
        temp = self.preferences.with_suffix(".tmp")
        temp.write_text(json.dumps({
            "media_folders": [str(p) for p in self._media_folders],
            "path_rewrites": self._rewrites,
        }, indent=2), encoding="utf-8")
        temp.replace(self.preferences)

    def set_media_folders(self, folders) -> None:
        self._media_folders = [Path(folder).expanduser().resolve() for folder in folders]
        self._save_preferences()

    def path_rewrites(self) -> list[dict]:
        return list(self._rewrites)

    def wait_for_resolution(self, timeout: float | None = None) -> bool:
        return self._resolution_done.wait(timeout)

    # -- paths and metadata ------------------------------------------------

    @staticmethod
    def media_id(digest: str) -> str:
        return f"m{digest[:12]}"

    def working_file(self, media_id: str) -> Path:
        return self.folder / f"{media_id}.flac"

    def _row(self, media_id: str) -> dict | None:
        with self._db_lock:
            cur = self.db.execute("select * from media where id=?", (media_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return dict(zip([c[0] for c in cur.description], row, strict=True))

    def meta(self, media_id: str) -> dict:
        """The media row, as a dict of its columns."""
        m = self._meta.get(media_id)
        if m is None:
            m = self._row(media_id)
            if m is None:
                raise KeyError(media_id)
            self._meta[media_id] = m
        return m

    def _update(self, media_id: str, **columns) -> None:
        self._check_writable()
        sets = ", ".join(f"{name}=?" for name in columns)
        with self._db_lock, dbm.tx(self.db):
            self.db.execute(f"update media set {sets} where id=?",  # noqa: S608 - names are ours
                            (*columns.values(), media_id))
        self._meta.pop(media_id, None)

    def _check_writable(self) -> None:
        if self.read_only:
            raise MediaError("error.media.read_only")

    def is_lossless(self, media_id: str) -> bool:
        return bool(self.meta(media_id)["lossless"])

    # -- identity ----------------------------------------------------------

    def find(self, path: str | Path) -> str | None:
        """The media id of these bytes if the store has them, by content alone."""
        media_id = self.media_id(_sha256(Path(path)))
        return media_id if self._row(media_id) is not None else None

    def seen_paths(self, digest: str) -> list[str]:
        with self._db_lock:
            rows = self.db.execute(
                "select path from media_paths where sha256=?"
                " order by first_seen_utc, rowid",
                (digest,)).fetchall()
        return [r[0] for r in rows]

    def _remember(self, digest: str, path: Path) -> None:
        if self.read_only:
            return
        now = dbm.utc_now()
        with self._db_lock, dbm.tx(self.db):
            self.db.execute(
                "insert into media_paths(sha256, path, first_seen_utc, last_seen_utc)"
                " values (?,?,?,?) on conflict(sha256, path)"
                " do update set last_seen_utc=excluded.last_seen_utc",
                (digest, str(path.resolve()), now, now))

    # -- import ------------------------------------------------------------

    def import_batch(self, paths, copy: bool = False) -> list[ImportResult]:
        """Import several files at once, one core each.

        One bad file never fails the batch: every outcome is an
        ``ImportResult``, in the order of ``paths``, with the reason for a
        failure and any warnings for a success.
        """
        paths = [Path(p) for p in paths]
        if not paths:
            return []
        with ThreadPoolExecutor(max_workers=min(len(paths), workers())) as pool:
            return list(pool.map(lambda path: self._attempt(path, copy), paths))

    def import_files(self, paths, copy: bool = False) -> list[Media]:
        """``import_batch`` for callers that want all or an error: every file is
        tried, then the first failure (if any) is raised."""
        results = self.import_batch(paths, copy)
        for r in results:
            if not r.ok:
                raise r.error
        return [r.media for r in results]

    def _attempt(self, path: Path, copy: bool) -> ImportResult:
        notes: list[Note] = []
        try:
            return ImportResult(path, self._import(path, copy, notes), None, notes)
        except KuulasError as e:
            err: Exception = e
        except Exception as e:  # noqa: BLE001 - whatever it is, it costs this file only
            err = self._explain(path, e, None) or MediaError(
                "error.media.failed", name=path.name, error=str(e) or type(e).__name__)
        log.warning(t("log.media.import_failed", name=path.name, error=str(err)))
        return ImportResult(path, None, err, notes)

    def import_file(self, path: str | Path, copy: bool = False) -> Media:
        """Bring ``path`` into the project. Importing the same bytes twice is free.

        ``copy=False`` (the default, like Final Cut's "leave files in place"):
        integer PCM at the project rate is *linked*, read where it lies. Any
        other source is decoded once to a FLAC working file either way, since
        decoding it during playback would be too slow. ``copy=True`` stores
        every source in the project (see ``consolidate``). Raises on failure;
        ``import_batch`` reports instead.
        """
        return self._import(Path(path), copy, [])

    def _import(self, path: Path, copy: bool, notes: list[Note]) -> Media:
        self._check_writable()
        path = path.resolve()
        digest = _sha256(path)
        media_id = self.media_id(digest)
        with self._lock:
            once = self._import_locks.setdefault(media_id, threading.Lock())
        with once:
            media = self._import_once(path, digest, media_id, copy, notes)
        # Remembered only once it is in: a refused file leaves no trace.
        self._remember(digest, path)
        return media

    def _import_once(self, path: Path, digest: str, media_id: str, copy: bool,
                     notes: list[Note]) -> Media:
        row = self._row(media_id)
        if row is not None and row["sha256"] != digest:
            # Two different files share the first 12 hex digits of their hash.
            raise MediaError("error.media.id_collision", name=path.name,
                             media_id=media_id)
        if row is None:
            self._import_new(path, digest, media_id, copy, notes)
        meta = self.meta(media_id)
        extra = json.loads(meta["extra"] or "{}")
        if row is not None and "partial" in extra:
            notes.append(self._partial_note(path.name, extra["partial"]))
        return Media(id=media_id, name=path.name, channels=meta["channels"],
                     frames=meta["source_frames"], sha256=digest,
                     time_ref_flicks=meta["time_ref_flicks"], extra=extra)

    def _import_new(self, path: Path, digest: str, media_id: str, copy: bool,
                    notes: list[Note]) -> None:
        pr = probe(path)
        self._check_source_rate(path)
        new = {"id": media_id, "sha256": digest, "name": path.name,
               "time_ref_flicks": self._time_reference(path, notes)}
        if pr.channels > 2:
            notes.append(Note("warn.media.downmixed", {"name": path.name,
                                                       "channels": pr.channels}))
        info = _pcm_info(path, self.rate)
        job = _Job(path, notes, pr)
        if info is None or copy:
            self._check_space(path, job, original=copy and info is None)
        with self._guarded(path, media_id, job):
            if info is not None and not copy:
                self._link(path, new, info, job)
            elif info is not None:
                self._encode_pcm(path, new, job)
            else:
                self._encode_any(path, new, keep_original=copy, job=job)

    def _time_reference(self, path: Path, notes: list[Note]) -> int | None:
        bwf = bwf_time_reference(path)
        if bwf is None:
            return None
        samples, file_rate = bwf
        hours = samples / file_rate / 3600 if file_rate else float("inf")
        if hours > MAX_TIME_REFERENCE_HOURS:
            notes.append(Note("warn.media.bad_time_reference",
                              {"name": path.name, "hours": round(hours, 1)}))
            return None
        return frames_to_flicks(samples, file_rate)

    def _check_space(self, path: Path, job: _Job, original: bool) -> None:
        """Refuse before decoding what the project's disk cannot hold."""
        frames = job.probe.frames(self.rate)
        if frames is None:
            return  # no length to estimate from; a full disk is still caught mid-write
        job.needed = frames * min(job.probe.channels, 2) * ESTIMATE_BYTES_PER_SAMPLE
        if original:
            job.needed += path.stat().st_size
        free = self._free()
        if free is not None and job.needed > free:
            raise MediaError("error.media.disk_full", **self._space(path, job, free))

    def _free(self) -> int | None:
        try:
            return shutil.disk_usage(self.folder).free
        except OSError:
            return None

    @staticmethod
    def _space(path: Path, job: _Job | None, free: int | None) -> dict:
        needed = job.needed if job else 0
        return {"name": path.name, "needed": needed, "free": free or 0,
                "needed_mb": _mb(needed), "free_mb": _mb(free or 0)}

    def _explain(self, path: Path, e: Exception, job: _Job | None) -> MediaError | None:
        """A full disk or a vanished source drive, in words; None for any
        other error."""
        if not isinstance(e, OSError):
            return None
        if e.errno == errno.ENOSPC:
            return MediaError("error.media.disk_full",
                              **self._space(path, job, self._free()))
        if e.errno in VANISHED_ERRNOS or not _exists(path):
            return MediaError("error.media.source_vanished", name=path.name,
                              drive=drive_of(path))
        return None

    @contextmanager
    def _guarded(self, path: Path, media_id: str, job: _Job):
        """Whatever goes wrong while writing, the half-written files go too
        (the row was never inserted, so nothing looks imported)."""
        try:
            yield
        except BaseException as e:
            self.working_file(media_id).with_suffix(".partial.flac").unlink(missing_ok=True)
            for half in (self.folder / "originals").glob(f"{media_id}*.partial"):
                half.unlink(missing_ok=True)
            mapped = self._explain(path, e, job)
            if mapped is not None:
                raise mapped from e
            raise

    def _partial_note(self, name: str, partial: dict) -> Note:
        got = _clock(partial["frames"], self.rate)
        if partial.get("expected_frames"):
            return Note("warn.media.partial", {
                "name": name, "got": got,
                "of": _clock(partial["expected_frames"], self.rate)})
        return Note("warn.media.partial_unknown", {"name": name, "got": got})

    def _settle(self, source: Path, job: _Job, row: dict, frames: int,
                damaged: bool) -> None:
        """After decoding: nothing at all is an error, a short decode of a file
        that promised more is a partial import, a lost source is neither."""
        rate = self.rate
        expected = job.probe.frames(rate)
        short = expected is not None and expected - frames > max(
            SHORTFALL_SEC * rate, SHORTFALL_FRACTION * expected)
        if (damaged or short or frames == 0) and not _exists(source):
            raise MediaError("error.media.source_vanished", name=source.name,
                             drive=drive_of(source))
        if frames == 0:
            raise MediaError("error.media.empty", name=source.name)
        if damaged or (short and job.probe.exact):
            partial = {"frames": frames, "expected_frames": expected}
            row["extra"] = json.dumps({"partial": partial})
            job.notes.append(self._partial_note(source.name, partial))

    @staticmethod
    def _check_source_rate(path: Path) -> None:
        """Refuse a file whose rate flicks cannot hold (``clock.check_rate``).

        Only formats libsndfile reads report a rate here; others are
        resampled by ffmpeg and carry no BWF time, so their rate never
        reaches the recording clock.
        """
        try:
            rate = sf.info(str(path)).samplerate
        except (sf.LibsndfileError, RuntimeError):
            return
        try:
            check_rate(rate)
        except RateError as e:
            raise MediaError(e.key, **e.params) from None

    def _peaks_path(self, digest: str) -> Path:
        k = caches.key([digest], {"per": PEAK_FRAMES, "rate": self.rate}, PEAKS_ALGORITHM)
        return caches.path(self.cache_root, "peaks", k, "npy")

    def _save_peaks(self, digest: str, peaks: np.ndarray) -> None:
        caches.write_atomic(self._peaks_path(digest), lambda f: np.save(f, peaks))

    def _finish(self, row: dict, peaks: list, job: _Job | None = None) -> None:
        """Peaks to the cache, then the row: inserted last, so it marks the
        import as finished. An existing row (consolidation) only gets its
        file columns updated. Digital silence is flagged, not refused: it may
        be a track that is meant to be quiet."""
        if job is not None and peaks and not any(p.any() for p in peaks):
            job.notes.append(Note("warn.media.silent", {"name": row["name"]}))
        base = np.concatenate(peaks) if peaks else np.zeros((0, 2), np.float32)
        self._save_peaks(row["sha256"], base)
        self._save_pyramid(row["sha256"], base)
        row = {"source_rate": self.rate, "linked_path": None, "linked_size": None,
               "linked_mtime_ns": None, "linked_package_rel": None,
               "linked_series_rel": None, "added_utc": dbm.utc_now(), **row}
        names = list(row)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _FILE_COLUMNS)
        with self._db_lock, dbm.tx(self.db):
            self.db.execute(
                f"insert into media({', '.join(names)}) values"  # noqa: S608 - names are ours
                f" ({', '.join('?' for _ in names)})"
                f" on conflict(id) do update set {updates}",
                [row[n] for n in names])
        self._meta.pop(row["id"], None)

    def _link(self, path: Path, row: dict, info, job: _Job | None = None) -> None:
        step = CHUNK_SEC * self.rate
        errors: list = []
        with sf.SoundFile(str(path)) as f:
            peaks, frames = _pump(lambda: _read_soft(f, step, "float32", errors))
        if job is not None:
            self._settle(path, job, row, frames, bool(errors))
        st = path.stat()
        self._finish({**row, "storage": "linked", "channels": info.channels,
                      "source_frames": frames, "subtype": info.subtype, "lossless": 1,
                      "linked_path": str(path), "linked_size": st.st_size,
                      "linked_mtime_ns": st.st_mtime_ns,
                      "linked_package_rel": _relative(path, self.package_root),
                      "linked_series_rel": _relative(path, self.series_root)}, peaks, job)

    def _encode_pcm(self, source: Path, row: dict, job: _Job | None = None) -> None:
        """Integer samples straight into FLAC: no float step, so bit-exact."""
        media_id = row["id"]
        info = sf.info(str(source))
        step = CHUNK_SEC * self.rate
        partial = self.working_file(media_id).with_suffix(".partial.flac")
        errors: list = []
        with sf.SoundFile(str(source)) as f, sf.SoundFile(
                str(partial), "w", self.rate, info.channels, subtype=info.subtype,
                format="FLAC") as out:
            def read():
                block = _read_soft(f, step, "int32", errors)
                out.write(block)
                return block / 2.0 ** 31
            peaks, frames = _pump(read)
        if job is not None:
            self._settle(source, job, row, frames, bool(errors))
        lossless = _same_samples(source, partial, step)
        if not lossless:
            self._keep_original(source, media_id)
        partial.replace(self.working_file(media_id))
        self._finish({**row, "storage": "working", "channels": info.channels,
                      "source_frames": frames, "subtype": info.subtype,
                      "lossless": int(lossless)}, peaks, job)

    def _encode_any(self, source: Path, row: dict, keep_original: bool,
                    job: _Job) -> None:
        """Anything ffmpeg can open, video included: first audio stream, 24-bit
        FLAC, at most two channels (more are downmixed)."""
        media_id = row["id"]
        channels = min(job.probe.channels, 2)
        partial = self.working_file(media_id).with_suffix(".partial.flac")
        step = CHUNK_SEC * self.rate
        with _ffmpeg_pcm(source, self.rate, channels) as dec, sf.SoundFile(
                str(partial), "w", self.rate, channels, subtype="PCM_24",
                format="FLAC") as out:
            def read():
                raw = dec.read(step * channels * 4)
                block = np.frombuffer(raw[: len(raw) // (4 * channels) * 4 * channels],
                                      dtype="<f4").reshape(-1, channels)
                out.write(block)
                return block
            peaks, frames = _pump(read)
        damaged = dec.timed_out or dec.returncode != 0 or bool(dec.errors)
        if frames == 0 and damaged and _exists(source):
            if dec.timed_out:
                raise MediaError("error.media.decode_timeout", name=source.name,
                                 seconds=round(dec.stall))
            raise MediaError("error.media.decode_failed", name=source.name,
                             error=dec.errors or f"exit code {dec.returncode}")
        self._settle(source, job, row, frames, damaged)
        if keep_original:
            self._keep_original(source, media_id)
        partial.replace(self.working_file(media_id))
        self._finish({**row, "storage": "working", "channels": channels,
                      "source_frames": frames, "subtype": "PCM_24", "lossless": 0},
                     peaks, job)

    def _keep_original(self, source: Path, media_id: str) -> None:
        originals = self.folder / "originals"
        originals.mkdir(exist_ok=True)
        kept = originals / f"{media_id}{source.suffix.lower()}"
        if not kept.exists():
            partial = kept.with_name(kept.name + ".partial")
            shutil.copy2(source, partial)
            partial.replace(kept)

    # -- linked files: missing, relink, consolidate -------------------------

    def is_linked(self, media_id: str) -> bool:
        return self.meta(media_id)["storage"] == "linked"

    def ids(self) -> list[str]:
        with self._db_lock:
            return [r[0] for r in self.db.execute("select id from media order by id")]

    def _valid(self, media_id: str) -> bool:
        """Is a linked file still there and still the same bytes?"""
        meta = self.meta(media_id)
        path = Path(self._resolved_paths.get(media_id, meta["linked_path"]))
        try:
            st = path.stat()
        except OSError:
            return False
        if st.st_size != meta["linked_size"]:
            return False
        if st.st_mtime_ns == meta["linked_mtime_ns"]:
            return True
        if _sha256(path) != meta["sha256"]:
            return False
        if not self.read_only:
            self._update(media_id, linked_mtime_ns=st.st_mtime_ns)  # touched, not changed
        return True

    def missing(self) -> list[str]:
        """Linked media whose file is gone, moved or changed."""
        lost = []
        for m in self.ids():
            if self.is_linked(m):
                ok = self._linked_ok[m] = self._valid(m)
                if not ok:
                    lost.append(m)
        return lost

    def _accept_path(self, media_id: str, path: Path, *, persist: bool = True) -> str:
        try:
            path = path.resolve()
            st = path.stat()
            digest = _sha256(path)
        except OSError:
            return ""
        meta = self.meta(media_id)
        if st.st_size != meta["linked_size"] or digest != meta["sha256"]:
            return ""
        where = str(path)
        self._resolved_paths[media_id] = where
        self._linked_ok[media_id] = True
        if persist and not self.read_only:
            self._update(media_id, linked_path=where, linked_size=st.st_size,
                         linked_mtime_ns=st.st_mtime_ns,
                         linked_package_rel=_relative(path, self.package_root),
                         linked_series_rel=_relative(path, self.series_root))
            self._remember(self.meta(media_id)["sha256"], path)
        with self._lock:
            old = self._handles.pop(media_id, None)
            if old:
                old[1].close()
        return where

    def _resolve_missing(self) -> None:
        try:
            lost = self.missing()
            candidates: list[Path] = []
            for media_id in lost:
                meta = self.meta(media_id)
                for rel, root in ((meta.get("linked_package_rel"), self.package_root),
                                  (meta.get("linked_series_rel"), self.series_root)):
                    if rel and root:
                        candidates.append(root / rel)
            for rewrite in self._rewrites:
                old, new = Path(rewrite["old"]), Path(rewrite["new"])
                for media_id in lost:
                    linked = Path(self.meta(media_id)["linked_path"])
                    try:
                        rel = linked.relative_to(old)
                    except ValueError:
                        continue
                    candidates.append(new / rel)
            candidates.extend(Path(p) for media_id in lost
                              for p in self.seen_paths(self.meta(media_id)["sha256"]))
            for path in candidates:
                if self._resolution_stop.is_set():
                    return
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                for media_id in lost:
                    matches_size = size == self.meta(media_id)["linked_size"]
                    if media_id not in self._resolved_paths and matches_size:
                        try:
                            if _sha256(path) == self.meta(media_id)["sha256"]:
                                self._accept_path(media_id, path, persist=False)
                        except OSError:
                            pass
            for folder in self._media_folders:
                for path in folder.rglob("*"):
                    if self._resolution_stop.is_set():
                        return
                    if not path.is_file():
                        continue
                    try:
                        size = path.stat().st_size
                    except OSError:
                        continue
                    for media_id in lost:
                        if self._resolution_stop.is_set():
                            return
                        matches_size = size == self.meta(media_id)["linked_size"]
                        if media_id not in self._resolved_paths and matches_size:
                            try:
                                if _sha256(path) == self.meta(media_id)["sha256"]:
                                    self._accept_path(media_id, path, persist=False)
                            except OSError:
                                pass
        finally:
            self._resolution_done.set()

    def relink_one(self, media_id: str, path: str | Path) -> dict[str, str]:
        self._check_writable()
        chosen = Path(path)
        old_path = Path(self.meta(media_id)["linked_path"])
        found: dict[str, str] = {}
        accepted = self._accept_path(media_id, chosen)
        if not accepted:
            return found
        found[media_id] = accepted
        try:
            old_parent = old_path.parent
            new_parent = chosen.resolve().parent
            common = 0
            for a, b in zip(reversed(old_parent.parts), reversed(new_parent.parts),
                            strict=False):
                if a != b:
                    break
                common += 1
            if common:
                old_root = Path(*old_parent.parts[:-common])
                new_root = Path(*new_parent.parts[:-common])
                if str(old_root) and str(new_root):
                    self._rewrites = [r for r in self._rewrites
                                      if r["old"] != str(old_root)]
                    self._rewrites.insert(0, {"old": str(old_root), "new": str(new_root)})
                    self._save_preferences()
                    for other in self.missing():
                        try:
                            linked = Path(self.meta(other)["linked_path"])
                            candidate = new_root / linked.relative_to(old_root)
                            value = self._accept_path(other, candidate)
                            if value:
                                found[other] = value
                        except (ValueError, OSError):
                            continue
        except (OSError, ValueError):
            pass
        return found

    def set_series_root(self, folder: str | Path | None) -> None:
        self.series_root = Path(folder) if folder else None

    def relink(self, search: str | Path | None = None) -> dict[str, str]:
        """Find missing linked files again by content: remembered paths first,
        then every file of the right size under ``search``."""
        found: dict[str, str] = {}
        lost = self.missing()
        if not lost:
            return found
        self._check_writable()
        by_size: dict[int, list[str]] = {}
        for media_id in lost:
            by_size.setdefault(self.meta(media_id)["linked_size"], []).append(media_id)
        candidates = [Path(p) for m in lost
                      for p in self.seen_paths(self.meta(m)["sha256"])]
        candidates += [p for folder in self._media_folders for p in folder.rglob("*")
                       if p.is_file()]
        if search is not None:
            candidates += [p for p in Path(search).rglob("*")
                           if p.is_file() and p.stat().st_size in by_size]
        for path in candidates:
            try:
                size = path.stat().st_size
            except OSError:
                continue
            waiting = [m for m in by_size.get(size, []) if m not in found]
            if not waiting:
                continue
            digest = _sha256(path)
            for media_id in waiting:
                if self.meta(media_id)["sha256"] == digest:
                    where = self._accept_path(media_id, path)
                    if where:
                        found[media_id] = where
        with self._lock:
            for media_id in found:
                self._handles.pop(media_id, None)
        return found

    def consolidate(self) -> list[str]:
        """Copy every linked file into the project as lossless FLAC."""
        done = []
        for media_id in self.ids():
            if self.is_linked(media_id) and self._valid(media_id):
                self._check_writable()
                self._linked_ok.pop(media_id, None)
                meta = self.meta(media_id)
                self._encode_pcm(Path(meta["linked_path"]),
                                 {"id": media_id, "sha256": meta["sha256"],
                                  "name": meta["name"]})
                with self._lock:
                    self._handles.pop(media_id, None)
                    for key in [k for k in self._cache if k[0] == media_id]:
                        del self._cache[key]
                done.append(media_id)
        return done

    # -- reading -----------------------------------------------------------

    def _handle(self, media_id: str) -> tuple[threading.Lock, sf.SoundFile] | None:
        with self._lock:
            h = self._handles.get(media_id)
        if h is not None:
            return h
        if self.is_linked(media_id):
            if not self._linked_ok.get(media_id, True):
                return None  # missing: plays as silence until relinked
            path = self._resolved_paths.get(media_id, self.meta(media_id)["linked_path"])
        else:
            path = str(self.working_file(media_id))
        with self._lock:
            h = self._handles.get(media_id)
            if h is None:
                h = (threading.Lock(), sf.SoundFile(path))
                self._handles[media_id] = h
            return h

    def _chunk(self, media_id: str, index: int) -> np.ndarray:
        key = (media_id, index)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        handle = self._handle(media_id)
        step = CHUNK_SEC * self.rate
        if handle is None:
            return np.zeros((self.meta(media_id)["channels"], step), dtype=np.float32)
        lock, f = handle
        with lock:
            f.seek(index * step)
            data = np.ascontiguousarray(f.read(step, dtype="float32", always_2d=True).T)
        with self._lock:
            self._cache[key] = data
            while len(self._cache) > CACHE_CHUNKS:
                self._cache.popitem(last=False)
        return data

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        """``(channels, count)`` float32 from source frame ``first``, zero-padded."""
        meta = self.meta(media_id)
        out = np.zeros((meta["channels"], count), dtype=np.float32)
        lo, hi = max(0, first), min(meta["source_frames"], first + count)
        step = CHUNK_SEC * self.rate
        pos = lo
        while pos < hi:
            index = pos // step
            data = self._chunk(media_id, index)
            a = pos - index * step
            n = min(hi - pos, data.shape[1] - a)
            if n <= 0:
                break
            out[:, pos - first:pos - first + n] = data[:, a:a + n]
            pos += n
        return out

    # -- waveform peaks ----------------------------------------------------

    def peaks(self, media_id: str, per: int = PEAK_FRAMES) -> np.ndarray:
        """``(n, 2)`` min/max per ``per`` frames (rounded to a multiple of the base)."""
        base = self._base_peaks(media_id)
        k = max(1, round(per / PEAK_FRAMES))
        n = int(np.ceil(base.shape[0] / k))
        padded = np.zeros((n * k, 2), dtype=np.float32)
        padded[: base.shape[0]] = base
        grouped = padded.reshape(n, k, 2)
        return np.stack([grouped[:, :, 0].min(axis=1), grouped[:, :, 1].max(axis=1)],
                        axis=1)

    def _base_peaks(self, media_id: str) -> np.ndarray:
        meta = self.meta(media_id)
        where = self._peaks_path(meta["sha256"])
        try:
            return np.load(where)
        except (OSError, ValueError, EOFError):
            pass  # deleted, or never written: compute again below
        log.info(t("log.cache.recompute", kind="peaks", media_id=media_id))
        step = CHUNK_SEC * self.rate
        frames = meta["source_frames"]
        pos = 0

        def read():
            nonlocal pos
            count = min(step, frames - pos)
            if count <= 0:
                return np.zeros((0, meta["channels"]), np.float32)
            block = self.read(media_id, pos, count).T
            pos += count
            return block
        peaks, _ = _pump(read)
        base = np.concatenate(peaks) if peaks else np.zeros((0, 2), np.float32)
        # A missing linked file reads as silence: show it, but never cache it.
        if not self._unreadable(media_id):
            self._save_peaks(meta["sha256"], base)
        return base

    # -- caches per recording (WP36) -----------------------------------------
    # Everything below is derived from the media's content, never from the
    # timeline, so an edit never touches it (PLAN ground rule 15).

    def _unreadable(self, media_id: str) -> bool:
        """A linked file that is gone reads as silence: never cache that."""
        return self.is_linked(media_id) and not self._linked_ok.get(media_id, True)

    def _save_pyramid(self, digest: str, base: np.ndarray) -> None:
        try:
            where = caches.path(self.cache_root, "peaks",
                                peak_pyramid.pyramid_key(digest, self.rate), "npz")
        except caches.CacheKeyError:
            log.warning(t("log.cache.no_key", kind="pyramid", media_id=digest[:12]))
            return
        peak_pyramid.save(where, peak_pyramid.build(base))

    def pyramid(self, media_id: str) -> dict[int, np.ndarray]:
        """``{frames per peak: (n, 2) min/max}`` for every level of the pyramid."""
        meta = self.meta(media_id)
        try:
            key = peak_pyramid.pyramid_key(meta["sha256"], self.rate)
        except caches.CacheKeyError:
            log.warning(t("log.cache.no_key", kind="pyramid", media_id=media_id))
            return peak_pyramid.build(self._base_peaks(media_id))
        where = caches.path(self.cache_root, "peaks", key, "npz")

        def load() -> dict[int, np.ndarray]:
            try:
                return peak_pyramid.load(where)
            except (OSError, ValueError, KeyError, EOFError):
                pass  # deleted, damaged or never written: build it again
            log.info(t("log.cache.recompute", kind="pyramid", media_id=media_id))
            levels_ = peak_pyramid.build(self._base_peaks(media_id))
            if not self._unreadable(media_id):
                peak_pyramid.save(where, levels_)
            return levels_

        if self._unreadable(media_id):
            return load()
        return self.budget.fetch("pyramid", key, load)

    def peak_tile(self, media_id: str, level: int, index: int) -> tuple[bytes, str]:
        """One tile of one level as ``(bytes, ETag)``; WP3 serves it over HTTP."""
        levels_ = self.pyramid(media_id)
        key = peak_pyramid.pyramid_key(self.meta(media_id)["sha256"], self.rate)
        return peak_pyramid.tile(levels_, key, level, index)

    def envelope(self, media_id: str, block: int) -> np.ndarray | None:
        """Energy per ``block`` frames of the whole file (``levels``), measured
        once and kept in ``caches/analysis/``. None when the file cannot be
        measured or keyed; the caller then reads the audio, which is the
        same measurement, only slower."""
        meta = self.meta(media_id)
        if self._unreadable(media_id):
            return None
        try:
            key = caches.key([meta["sha256"]], {"block": block, "rate": self.rate},
                             levels.ALGORITHM)
        except caches.CacheKeyError:
            log.warning(t("log.cache.no_key", kind="levels", media_id=media_id))
            return None

        def measure() -> np.ndarray:
            log.info(t("log.cache.recompute", kind="levels", media_id=media_id))
            return levels.block_energy(
                lambda first, count: self.read(media_id, first, count),
                meta["source_frames"], block)

        spill = caches.path(self.cache_root, "analysis", key, "npy")
        return self.budget.fetch("levels", key, measure, spill=spill)


def _peaks(chunk: np.ndarray) -> np.ndarray:
    mono = chunk.mean(axis=0) if chunk.shape[0] > 1 else chunk[0]
    n = int(np.ceil(mono.shape[0] / PEAK_FRAMES))
    padded = np.zeros(n * PEAK_FRAMES, dtype=np.float32)
    padded[: mono.shape[0]] = mono
    blocks = padded.reshape(n, PEAK_FRAMES)
    return np.stack([blocks.min(axis=1), blocks.max(axis=1)], axis=1).astype(np.float32)


def _pump(read) -> tuple[list, int]:
    """Call ``read()`` for (frames x channels) blocks until empty; collect peaks."""
    peaks, frames = [], 0
    while True:
        block = read()
        if block.shape[0] == 0:
            return peaks, frames
        peaks.append(_peaks(np.asarray(block.T, dtype=np.float32)))
        frames += block.shape[0]


def _pcm_info(path: Path, rate: int):
    """libsndfile's view of ``path`` if it is integer PCM at ``rate``, else None."""
    try:
        info = sf.info(str(path))
    except (sf.LibsndfileError, RuntimeError):
        return None
    if info.samplerate == rate and info.subtype in PCM_SUBTYPES and info.channels <= 2:
        return info
    return None


def _read_soft(f: sf.SoundFile, step: int, dtype: str, errors: list) -> np.ndarray:
    """``f.read`` that treats a decode error as the end of the file: what was
    read before it is kept, and the error is noted so the import is marked
    partial."""
    try:
        return f.read(step, dtype=dtype, always_2d=True)
    except sf.LibsndfileError as e:
        errors.append(e)
        return np.zeros((0, f.channels), dtype=dtype)


class _ffmpeg_pcm:  # noqa: N801 - used as a context manager, reads like a function
    """ffmpeg decoding the first audio stream to float32 at ``rate``.

    A watchdog kills it when ``read`` has delivered nothing for ``STALL_SEC``
    (``timed_out``). It does not raise for a failing decode: after the block,
    ``returncode``, ``errors`` (what ffmpeg said) and ``timed_out`` let the
    caller keep the audio that did come out.
    """

    def __init__(self, path: Path, rate: int, channels: int):
        self.path = path
        self.stall = STALL_SEC
        self.timed_out = False
        self.errors = ""
        self.returncode: int | None = None
        self._kept = b""
        self._last = time.monotonic()
        self._done = threading.Event()
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [get_binary_path("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path),
             "-map", "0:a:0", "-vn", "-ac", str(channels), "-ar", str(rate),
             "-f", "f32le", "-"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # stderr is drained as it comes: a file full of damage makes ffmpeg
        # write more than a pipe holds, and it would block on us.
        self._drain = threading.Thread(target=self._drain_stderr, daemon=True)
        self._watch = threading.Thread(target=self._watchdog, daemon=True)
        self._drain.start()
        self._watch.start()

    def _drain_stderr(self) -> None:
        keep = bytearray()
        while chunk := self.proc.stderr.read(4096):
            keep += chunk[: max(0, 4000 - len(keep))]
        self._kept = bytes(keep)

    def _watchdog(self) -> None:
        while not self._done.wait(min(1.0, self.stall / 4)):
            if time.monotonic() - self._last > self.stall:
                self.timed_out = True
                self.proc.kill()
                return

    def read(self, n: int) -> bytes:
        data = self.proc.stdout.read(n)
        self._last = time.monotonic()
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._done.set()
        if exc[0] is not None:
            self.proc.kill()
        self.proc.stdout.close()
        self.returncode = self.proc.wait()
        self._drain.join(timeout=5)
        self.proc.stderr.close()
        self.errors = self._kept.decode(errors="replace").strip()
        return False


class MediaError(KuulasError, RuntimeError):
    """A file could not be brought into the project."""


def _same_samples(a: Path, b: Path, step: int) -> bool:
    """Do two files hold identical integer samples? Read side by side in chunks."""
    with sf.SoundFile(str(a)) as fa, sf.SoundFile(str(b)) as fb:
        if fa.frames != fb.frames or fa.channels != fb.channels:
            return False
        while True:
            x = fa.read(step, dtype="int32")
            y = fb.read(step, dtype="int32")
            if len(x) == 0 and len(y) == 0:
                return True
            if not np.array_equal(x, y):
                return False
