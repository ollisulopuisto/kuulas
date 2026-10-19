"""Progressive WAV files: valid at every moment, repaired after a crash.

A take is written as mono 24-bit PCM WAV. The header is written first, before
any audio, and its two size fields (RIFF and data) are rewritten in place at
every flush, after the audio they cover has been synced. So at any moment the
file on disk is a valid WAV holding everything up to the last flush; nothing
waits for a clean stop. Bytes written after the last flush are past the end the
header names, which every reader ignores, and ``repair_wav`` takes them back.

Why 24-bit integer PCM and not 32-bit float: the plan (WP12) asks for it, it is
what every editor and archive tool reads, a microphone's converter has no more
than 24 bits to give, and it is a quarter smaller than float (144 000 bytes a
second at 48 kHz, so one file holds 8.2 hours before the RIFF limit).

Why the plain PCM format tag (1) and not WAVE_FORMAT_EXTENSIBLE: the file is
mono, so there is no channel mask to carry, and the plain tag is readable by
the oldest tools; libsndfile, ffmpeg, CoreAudio and Hindenburg all read 24-bit
plain PCM.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HEADER_BYTES = 44
BYTES_PER_FRAME = 3  # mono, 24-bit
BITS = 24

# The RIFF size field is 32 bits. Stop each file a megabyte short of it; the
# recorder continues in the next numbered file without losing a frame.
_RIFF_LIMIT = 0xFFFFFFFF - HEADER_BYTES - (1 << 20)
MAX_DATA_BYTES = _RIFF_LIMIT // BYTES_PER_FRAME * BYTES_PER_FRAME

_FULL_SCALE = float(1 << 23)


class WavRepairError(Exception):
    """A file that cannot be repaired, with a stable ``key``."""

    def __init__(self, key: str, text: str):
        super().__init__(text)
        self.key = key
        self.text = text


def header(rate: int, data_bytes: int) -> bytes:
    """The 44-byte header of a mono 24-bit PCM WAV with ``data_bytes`` of audio."""
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_bytes, b"WAVE",
        b"fmt ", 16, 1, 1, rate, rate * BYTES_PER_FRAME, BYTES_PER_FRAME, BITS,
        b"data", data_bytes,
    )


def float_to_pcm24(samples: np.ndarray) -> bytes:
    """Float samples (nominal -1..1) as little-endian 24-bit PCM, clipped."""
    scaled = np.rint(np.asarray(samples, dtype=np.float64) * _FULL_SCALE)
    ints = np.clip(scaled, -_FULL_SCALE, _FULL_SCALE - 1).astype("<i4")
    return ints.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()


# <sys/fcntl.h> on macOS; Python's fcntl module does not export it (3.13).
_F_BARRIERFSYNC = 85


def _mac_sync(fd: int, op: int) -> None:
    try:
        fcntl.fcntl(fd, op)
    except OSError:
        # Some file systems (network shares, FAT) refuse these; plain fsync then.
        os.fsync(fd)


def full_sync(fd: int) -> None:
    """Make the file's data durable, through the drive's own cache on macOS.

    Plain ``fsync`` on macOS only hands the data to the drive, which may still
    lose it on a power cut; ``F_FULLFSYNC`` asks the drive to flush too.
    Measured on the owner's Mac Studio (2026-10-19): 4 ms median, 27 ms worst
    per call, against 0.1 ms for ``fsync``. Called once a flush per file.
    """
    if sys.platform == "darwin" and hasattr(fcntl, "F_FULLFSYNC"):
        _mac_sync(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


def ordered_sync(fd: int) -> None:
    """Sync so that everything written before reaches the disk before anything
    written after: on macOS ``F_BARRIERFSYNC`` (0.8 ms median measured), a
    plain ``fsync`` elsewhere. Used between the audio and the header naming it."""
    if sys.platform == "darwin":
        _mac_sync(fd, _F_BARRIERFSYNC)
    else:
        os.fsync(fd)


def sync_dir(path: Path) -> None:
    """Make a new or renamed directory entry durable (best effort)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class ProgressiveWav:
    """One mono 24-bit WAV that grows, valid on disk after every ``flush``.

    ``write`` appends audio; ``flush`` syncs the audio, rewrites the header to
    cover it and syncs again, in that order, so the header never names audio
    that is not on disk yet. The file is created exclusively: an existing file
    is never overwritten.
    """

    def __init__(self, path: Path | str, rate: int, *,
                 max_data_bytes: int = MAX_DATA_BYTES):
        self.path = Path(path)
        self.rate = rate
        self.max_data_bytes = max_data_bytes - max_data_bytes % BYTES_PER_FRAME
        self.data_bytes = 0  # bytes fully written after the header
        self.flushed_bytes = 0  # bytes the header on disk covers
        self._fd: int | None = os.open(
            self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            self._write_all(header(rate, 0))
            full_sync(self._fd)
        except BaseException:
            self.abandon()
            raise
        sync_dir(self.path.parent)

    @property
    def frames(self) -> int:
        return self.data_bytes // BYTES_PER_FRAME

    @property
    def flushed_frames(self) -> int:
        return self.flushed_bytes // BYTES_PER_FRAME

    def fileno(self) -> int:
        if self._fd is None:
            raise ValueError("file is closed")
        return self._fd

    def room_frames(self) -> int:
        return (self.max_data_bytes - self.data_bytes) // BYTES_PER_FRAME

    def _write_all(self, data: bytes | memoryview) -> None:
        view = memoryview(data)
        while view:
            n = os.write(self.fileno(), view)
            view = view[n:]

    def write(self, pcm: bytes) -> None:
        """Append whole frames. On an error (a full disk) the partial tail is cut
        off again so the file still ends on a frame, and the error is raised."""
        if len(pcm) % BYTES_PER_FRAME:
            raise ValueError("audio must be whole 24-bit frames")
        if self.data_bytes + len(pcm) > self.max_data_bytes:
            raise ValueError("write would pass the file size limit")
        try:
            self._write_all(pcm)
        except OSError:
            with contextlib.suppress(OSError):
                os.ftruncate(self.fileno(), HEADER_BYTES + self.data_bytes)
            raise
        self.data_bytes += len(pcm)

    def flush(self) -> None:
        """Sync the audio, then the header that covers it. Nothing is buffered in
        Python (``os.write``), so this is the only durability step. The barrier
        keeps the header from reaching the disk before the audio it names; the
        full sync after it makes both durable."""
        fd = self.fileno()
        if self.data_bytes != self.flushed_bytes:
            ordered_sync(fd)
            os.pwrite(fd, header(self.rate, self.data_bytes), 0)
            full_sync(fd)
            self.flushed_bytes = self.data_bytes

    def close(self) -> None:
        if self._fd is None:
            return
        try:
            self.flush()
        finally:
            os.close(self._fd)
            self._fd = None

    def abandon(self) -> None:
        """Close without a final header update: what a killed process leaves."""
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


@dataclass(frozen=True)
class RepairResult:
    path: str
    frames: int  # whole frames in the file after the repair
    changed: bool  # the file was rewritten
    trimmed_bytes: int  # bytes of a partial last frame that were cut off


def _chunks(head: bytes):
    """(id, size, offset of its body) for each chunk header found in ``head``."""
    pos = 12
    while pos + 8 <= len(head):
        cid, size = struct.unpack_from("<4sI", head, pos)
        yield cid, size, pos + 8
        if cid == b"data":
            return
        pos += 8 + size + (size & 1)


def repair_wav(path: Path | str, *, rate: int = 48000) -> RepairResult:
    """Make a WAV from a killed or power-cut recorder readable with all its audio.

    The data chunk is taken to run to the end of the file (it is the last chunk
    in every file the recorder writes): its size and the RIFF size are set to
    the whole frames present, and a partial last frame is cut off. Audio written
    after the last flush is kept. A file whose header never reached the disk is
    rebuilt as an empty mono 24-bit WAV at ``rate``. A file that is not a WAV at
    all raises ``WavRepairError`` and is left untouched.
    """
    path = Path(path)
    size = path.stat().st_size
    with open(path, "r+b") as f:
        head = f.read(min(size, 1 << 16))
        if size < HEADER_BYTES and (not head or b"RIFF".startswith(head[:4])
                                    or head.startswith(b"RIFF")):
            f.seek(0)
            f.write(header(rate, 0))
            f.truncate(HEADER_BYTES)
            f.flush()
            full_sync(f.fileno())
            return RepairResult(str(path), 0, True, 0)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise WavRepairError("not_a_wav", f"{path.name} is not a WAV file")
        fmt = data = None
        for cid, csize, body in _chunks(head):
            if cid == b"fmt " and body + 16 <= len(head):
                fmt = struct.unpack_from("<HHIIHH", head, body)
            elif cid == b"data":
                data = (csize, body)
        if fmt is None or data is None:
            raise WavRepairError("no_audio_chunk",
                                 f"{path.name} has no readable format or data chunk")
        block_align = fmt[4] or BYTES_PER_FRAME
        declared, body = data
        available = size - body
        whole = available // block_align * block_align
        trimmed = available - whole
        riff = body + whole - 8
        current_riff = struct.unpack_from("<I", head, 4)[0]
        if declared == whole and trimmed == 0 and current_riff == riff:
            return RepairResult(str(path), whole // block_align, False, 0)
        f.seek(4)
        f.write(struct.pack("<I", riff))
        f.seek(body - 4)
        f.write(struct.pack("<I", whole))
        if trimmed:
            f.truncate(body + whole)
        f.flush()
        full_sync(f.fileno())
        return RepairResult(str(path), whole // block_align, True, trimmed)


def wav_frames(path: Path | str) -> int:
    """Frames the header of a recorder WAV names (no repair, no audio read)."""
    with open(path, "rb") as f:
        head = f.read(1 << 16)
    for cid, csize, _body in _chunks(head):
        if cid == b"data":
            return csize // BYTES_PER_FRAME
    return 0
