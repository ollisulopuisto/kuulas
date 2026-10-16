"""Imported audio, stored once as FLAC at the project rate.

**Identity is the content, never the name.** A media id is the SHA-256 of
the file's bytes, so a file that was renamed, moved or copied is the same
media; ``seen.json`` remembers every path each hash has been seen under.

**Storage.** Each source becomes one FLAC working file at the project rate:

* Integer PCM already at the project rate is written at its own bit depth
  and checked sample by sample against the source. When it matches, the
  FLAC *is* the original and no other copy is kept.
* Anything else (resampled, float, lossy) becomes 24-bit FLAC, and the
  original file is kept beside it in ``originals/``.

A project folder is complete on its own: moving or deleting the source
cannot break it.

**Reading.** The mixer asks for arbitrary slices on the audio thread, so
reads go through a cache of decoded chunks; FLAC seeks are sample-exact.
"""

from __future__ import annotations

import hashlib
import json
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

from .model import Media

#: Frames per peak at the finest zoom level the UI asks for.
PEAK_FRAMES = 256
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


class MediaStore:
    def __init__(self, folder: str | Path, rate: int):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.rate = rate
        self._lock = threading.Lock()
        self._handles: dict[str, tuple[threading.Lock, sf.SoundFile]] = {}
        self._cache: OrderedDict[tuple[str, int], np.ndarray] = OrderedDict()
        self._meta: dict[str, dict] = {}

    # -- paths and metadata ------------------------------------------------

    @staticmethod
    def media_id(digest: str) -> str:
        return f"m{digest[:12]}"

    def working_file(self, media_id: str) -> Path:
        return self.folder / f"{media_id}.flac"

    def _meta_path(self, media_id: str) -> Path:
        return self.folder / f"{media_id}.json"

    def meta(self, media_id: str) -> dict:
        m = self._meta.get(media_id)
        if m is None:
            m = json.loads(self._meta_path(media_id).read_text())
            self._meta[media_id] = m
        return m

    def is_lossless(self, media_id: str) -> bool:
        return bool(self.meta(media_id)["lossless"])

    # -- identity ----------------------------------------------------------

    def find(self, path: str | Path) -> str | None:
        """The media id of these bytes if the store has them, by content alone."""
        media_id = self.media_id(_sha256(Path(path)))
        return media_id if self._meta_path(media_id).exists() else None

    def _seen_index(self) -> dict[str, list[str]]:
        try:
            return json.loads((self.folder / "seen.json").read_text())
        except FileNotFoundError:
            return {}

    def seen_paths(self, digest: str) -> list[str]:
        return self._seen_index().get(digest, [])

    def _remember(self, digest: str, path: Path) -> None:
        with self._lock:
            index = self._seen_index()
            paths = index.setdefault(digest, [])
            where = str(path.resolve())
            if where not in paths:
                paths.append(where)
                tmp = self.folder / "seen.json.tmp"
                tmp.write_text(json.dumps(index, indent=1))
                tmp.replace(self.folder / "seen.json")

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
        path = Path(path).resolve()
        digest = _sha256(path)
        media_id = self.media_id(digest)
        self._remember(digest, path)
        if not self._meta_path(media_id).exists():
            info = _pcm_info(path, self.rate)
            if info is not None and not copy:
                self._link(path, media_id, digest, info)
            elif info is not None:
                self._encode_pcm(path, media_id, digest)
            else:
                self._encode_any(path, media_id, digest, keep_original=copy)
        meta = self.meta(media_id)
        bwf = bwf_time_reference(path)
        time_ref = round(bwf[0] * self.rate / bwf[1]) if bwf else 0
        return Media(id=media_id, name=path.name, channels=meta["channels"],
                     frames=meta["frames"], sha256=digest, time_ref=time_ref)

    def _finish(self, media_id: str, peaks: list, meta: dict) -> None:
        np.save(self.folder / f"{media_id}.peaks.npy",
                np.concatenate(peaks) if peaks else np.zeros((0, 2), np.float32))
        # The metadata file is what marks the media as imported, so it is
        # written last: a crash mid-import leaves nothing that looks done.
        tmp = self._meta_path(media_id).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(meta))
        tmp.replace(self._meta_path(media_id))
        self._meta[media_id] = meta

    def _link(self, path: Path, media_id: str, digest: str, info) -> None:
        step = CHUNK_SEC * self.rate
        with sf.SoundFile(str(path)) as f:
            peaks, frames = _pump(lambda: f.read(step, dtype="float32", always_2d=True))
        st = path.stat()
        self._finish(media_id, peaks, {
            "channels": info.channels, "frames": frames, "subtype": info.subtype,
            "lossless": True, "linked": True, "path": str(path),
            "size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": digest})

    def _encode_pcm(self, source: Path, media_id: str, digest: str) -> None:
        """Integer samples straight into FLAC: no float step, so bit-exact."""
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
        self._finish(media_id, peaks, {
            "channels": info.channels, "frames": frames, "subtype": info.subtype,
            "lossless": lossless, "linked": False, "sha256": digest})

    def _encode_any(self, source: Path, media_id: str, digest: str,
                    keep_original: bool) -> None:
        """Anything ffmpeg can open, video included: first audio stream, 24-bit FLAC."""
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
        self._finish(media_id, peaks, {
            "channels": channels, "frames": frames, "subtype": "PCM_24",
            "lossless": False, "linked": False, "source": str(source),
            "sha256": digest})

    def _keep_original(self, source: Path, media_id: str) -> None:
        originals = self.folder / "originals"
        originals.mkdir(exist_ok=True)
        kept = originals / f"{media_id}{source.suffix.lower()}"
        if not kept.exists():
            shutil.copy2(source, kept)

    # -- linked files: missing, relink, consolidate -------------------------

    def is_linked(self, media_id: str) -> bool:
        return bool(self.meta(media_id).get("linked"))

    def _all_ids(self) -> list[str]:
        return sorted(p.stem for p in self.folder.glob("m*.json"))

    def _valid(self, media_id: str) -> bool:
        """Is a linked file still there and still the same bytes?"""
        meta = self.meta(media_id)
        path = Path(meta["path"])
        try:
            st = path.stat()
        except OSError:
            return False
        if st.st_size != meta["size"]:
            return False
        if st.st_mtime_ns == meta["mtime_ns"]:
            return True
        if _sha256(path) != meta["sha256"]:
            return False
        meta["mtime_ns"] = st.st_mtime_ns  # touched, not changed
        self._finish_meta(media_id, meta)
        return True

    def _finish_meta(self, media_id: str, meta: dict) -> None:
        tmp = self._meta_path(media_id).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(meta))
        tmp.replace(self._meta_path(media_id))
        self._meta[media_id] = meta

    def missing(self) -> list[str]:
        """Linked media whose file is gone, moved or changed."""
        return [m for m in self._all_ids() if self.is_linked(m) and not self._valid(m)]

    def relink(self, search: str | Path | None = None) -> dict[str, str]:
        """Find missing linked files again by content: remembered paths first,
        then every file of the right size under ``search``."""
        found: dict[str, str] = {}
        lost = self.missing()
        if not lost:
            return found
        by_size: dict[int, list[str]] = {}
        for media_id in lost:
            by_size.setdefault(self.meta(media_id)["size"], []).append(media_id)
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
                meta = self.meta(media_id)
                if meta["sha256"] == digest:
                    meta.update(path=str(path.resolve()),
                                mtime_ns=path.stat().st_mtime_ns)
                    self._finish_meta(media_id, meta)
                    self._remember(digest, path)
                    found[media_id] = meta["path"]
        with self._lock:
            for media_id in found:
                self._handles.pop(media_id, None)
        return found

    def consolidate(self) -> list[str]:
        """Copy every linked file into the project as lossless FLAC."""
        done = []
        for media_id in self._all_ids():
            if self.is_linked(media_id) and self._valid(media_id):
                meta = self.meta(media_id)
                self._encode_pcm(Path(meta["path"]), media_id, meta["sha256"])
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
            path = self.meta(media_id)["path"]
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
        lo, hi = max(0, first), min(meta["frames"], first + count)
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
        base = np.load(self.folder / f"{media_id}.peaks.npy")
        k = max(1, round(per / PEAK_FRAMES))
        n = int(np.ceil(base.shape[0] / k))
        padded = np.zeros((n * k, 2), dtype=np.float32)
        padded[: base.shape[0]] = base
        grouped = padded.reshape(n, k, 2)
        return np.stack([grouped[:, :, 0].min(axis=1), grouped[:, :, 1].max(axis=1)],
                        axis=1)


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
        raise MediaError(f"{path.name}: no audio stream found")
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
            raise MediaError(f"{self.path.name}: ffmpeg could not decode it: {err}")
        return False


class MediaError(RuntimeError):
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
