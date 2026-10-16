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

**Reading.** The mixer asks for arbitrary slices on the audio thread, so
reads go through a cache of decoded chunks; FLAC seeks are sample-exact.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import struct
import subprocess
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def bwf_time_reference(path: Path) -> tuple[int, int] | None:
    """``(TimeReference samples, file rate)`` from a WAV's ``bext`` chunk, if any.

    Field recorders write the recording's start (samples since midnight)
    there; it is how files from one shoot line up without listening.
    """
    rate = None
    with path.open("rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
            return None
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                return None
            cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
            if cid == b"fmt ":
                fmt = f.read(size)
                rate = struct.unpack_from("<I", fmt, 4)[0]
            elif cid == b"bext" and size >= 346:
                bext = f.read(size)
                if rate is None:
                    return None
                return struct.unpack_from("<Q", bext, 338)[0], rate
            else:
                f.seek(size, 1)
            if size % 2:
                f.seek(1, 1)


def workers() -> int:
    """Parallel jobs for imports and analysis: every core but one for the UI."""
    return max(1, (os.cpu_count() or 2) - 1)


#: Columns an import or a consolidation sets; the rest of a row (name, time
#: reference, tags, extra, unknown columns) is never touched by them.
_FILE_COLUMNS = ("storage", "channels", "source_rate", "source_frames", "subtype",
                 "lossless", "linked_path", "linked_size", "linked_mtime_ns")


class MediaStore:
    """``folder`` is the package's ``media/``. The database and ``caches/``
    default to its siblings, as in a package (docs/FORMAT.md, "Layout")."""

    def __init__(self, folder: str | Path, rate: int, *, db: str | Path | None = None,
                 cache_root: str | Path | None = None, read_only: bool = False,
                 budget: MemoryBudget | None = None):
        self.budget = BUDGET if budget is None else budget
        self.folder = Path(folder)
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

    def close(self) -> None:
        with self._lock:
            for _, f in self._handles.values():
                f.close()
            self._handles.clear()
        self.db.close()

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

    def import_files(self, paths, copy: bool = False) -> list[Media]:
        """Import several files at once, one core each."""
        paths = list(paths)
        with ThreadPoolExecutor(max_workers=min(len(paths), workers()) or 1) as pool:
            return list(pool.map(lambda path: self.import_file(path, copy), paths))

    def import_file(self, path: str | Path, copy: bool = False) -> Media:
        """Bring ``path`` into the project. Importing the same bytes twice is free.

        ``copy=False`` (the default, like Final Cut's "leave files in place"):
        integer PCM at the project rate is *linked*, read where it lies. Any
        other source is decoded once to a FLAC working file either way, since
        decoding it during playback would be too slow. ``copy=True`` stores
        every source in the project (see ``consolidate``).
        """
        self._check_writable()
        path = Path(path).resolve()
        digest = _sha256(path)
        media_id = self.media_id(digest)
        self._remember(digest, path)
        with self._lock:
            once = self._import_locks.setdefault(media_id, threading.Lock())
        with once:
            return self._import_once(path, digest, media_id, copy)

    def _import_once(self, path: Path, digest: str, media_id: str, copy: bool) -> Media:
        row = self._row(media_id)
        if row is not None and row["sha256"] != digest:
            # Two different files share the first 12 hex digits of their hash.
            raise MediaError("error.media.id_collision", name=path.name,
                             media_id=media_id)
        if row is None:
            self._check_source_rate(path)
            bwf = bwf_time_reference(path)
            new = {"id": media_id, "sha256": digest, "name": path.name,
                   "time_ref_flicks": frames_to_flicks(*bwf) if bwf else None}
            info = _pcm_info(path, self.rate)
            if info is not None and not copy:
                self._link(path, new, info)
            elif info is not None:
                self._encode_pcm(path, new)
            else:
                self._encode_any(path, new, keep_original=copy)
        meta = self.meta(media_id)
        return Media(id=media_id, name=path.name, channels=meta["channels"],
                     frames=meta["source_frames"], sha256=digest,
                     time_ref_flicks=meta["time_ref_flicks"])

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

    def _finish(self, row: dict, peaks: list) -> None:
        """Peaks to the cache, then the row: inserted last, so it marks the
        import as finished. An existing row (consolidation) only gets its
        file columns updated."""
        base = np.concatenate(peaks) if peaks else np.zeros((0, 2), np.float32)
        self._save_peaks(row["sha256"], base)
        self._save_pyramid(row["sha256"], base)
        row = {"source_rate": self.rate, "linked_path": None, "linked_size": None,
               "linked_mtime_ns": None, "added_utc": dbm.utc_now(), **row}
        names = list(row)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _FILE_COLUMNS)
        with self._db_lock, dbm.tx(self.db):
            self.db.execute(
                f"insert into media({', '.join(names)}) values"  # noqa: S608 - names are ours
                f" ({', '.join('?' for _ in names)})"
                f" on conflict(id) do update set {updates}",
                [row[n] for n in names])
        self._meta.pop(row["id"], None)

    def _link(self, path: Path, row: dict, info) -> None:
        step = CHUNK_SEC * self.rate
        with sf.SoundFile(str(path)) as f:
            peaks, frames = _pump(lambda: f.read(step, dtype="float32", always_2d=True))
        st = path.stat()
        self._finish({**row, "storage": "linked", "channels": info.channels,
                      "source_frames": frames, "subtype": info.subtype, "lossless": 1,
                      "linked_path": str(path), "linked_size": st.st_size,
                      "linked_mtime_ns": st.st_mtime_ns}, peaks)

    def _encode_pcm(self, source: Path, row: dict) -> None:
        """Integer samples straight into FLAC: no float step, so bit-exact."""
        media_id = row["id"]
        info = sf.info(str(source))
        step = CHUNK_SEC * self.rate
        partial = self.working_file(media_id).with_suffix(".partial.flac")
        with sf.SoundFile(str(source)) as f, sf.SoundFile(
                str(partial), "w", self.rate, info.channels, subtype=info.subtype,
                format="FLAC") as out:
            def read():
                block = f.read(step, dtype="int32", always_2d=True)
                out.write(block)
                return block / 2.0 ** 31
            peaks, frames = _pump(read)
        lossless = _same_samples(source, partial, step)
        if not lossless:
            self._keep_original(source, media_id)
        partial.replace(self.working_file(media_id))
        self._finish({**row, "storage": "working", "channels": info.channels,
                      "source_frames": frames, "subtype": info.subtype,
                      "lossless": int(lossless)}, peaks)

    def _encode_any(self, source: Path, row: dict, keep_original: bool) -> None:
        """Anything ffmpeg can open, video included: first audio stream, 24-bit FLAC."""
        media_id = row["id"]
        channels = min(_ffprobe_channels(source), 2)
        partial = self.working_file(media_id).with_suffix(".partial.flac")
        step = CHUNK_SEC * self.rate
        with _ffmpeg_pcm(source, self.rate, channels) as pipe, sf.SoundFile(
                str(partial), "w", self.rate, channels, subtype="PCM_24",
                format="FLAC") as out:
            def read():
                raw = pipe.read(step * channels * 4)
                block = np.frombuffer(raw[: len(raw) // (4 * channels) * 4 * channels],
                                      dtype="<f4").reshape(-1, channels)
                out.write(block)
                return block
            peaks, frames = _pump(read)
        if keep_original:
            self._keep_original(source, media_id)
        partial.replace(self.working_file(media_id))
        self._finish({**row, "storage": "working", "channels": channels,
                      "source_frames": frames, "subtype": "PCM_24", "lossless": 0},
                     peaks)

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
        path = Path(meta["linked_path"])
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
        return [m for m in self.ids() if self.is_linked(m) and not self._valid(m)]

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
                    where = str(path.resolve())
                    self._update(media_id, linked_path=where,
                                 linked_mtime_ns=path.stat().st_mtime_ns)
                    self._remember(digest, path)
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
            if not self._valid(media_id):
                return None  # missing: plays as silence until relinked
            path = self.meta(media_id)["linked_path"]
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
        if not (self.is_linked(media_id) and not self._valid(media_id)):
            self._save_peaks(meta["sha256"], base)
        return base

    # -- caches per recording (WP36) -----------------------------------------
    # Everything below is derived from the media's content, never from the
    # timeline, so an edit never touches it (PLAN ground rule 15).

    def _unreadable(self, media_id: str) -> bool:
        """A linked file that is gone reads as silence: never cache that."""
        return self.is_linked(media_id) and not self._valid(media_id)

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


def _ffprobe_channels(path: Path) -> int:
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [get_binary_path("ffprobe"), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=channels", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL)
    text = out.stdout.strip().splitlines()
    if out.returncode != 0 or not text:
        raise MediaError("error.media.no_audio", name=path.name)
    return int(text[0])


class _ffmpeg_pcm:  # noqa: N801 - used as a context manager, reads like a function
    """ffmpeg decoding the first audio stream to float32 at ``rate``."""

    def __init__(self, path: Path, rate: int, channels: int):
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [get_binary_path("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path),
             "-map", "0:a:0", "-vn", "-ac", str(channels), "-ar", str(rate),
             "-f", "f32le", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.path = path

    def __enter__(self):
        return self.proc.stdout

    def __exit__(self, *exc):
        self.proc.stdout.close()
        err = self.proc.stderr.read().decode(errors="replace").strip()
        self.proc.stderr.close()
        if self.proc.wait() != 0 and exc[0] is None:
            raise MediaError("error.media.decode_failed", name=self.path.name, error=err)
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
