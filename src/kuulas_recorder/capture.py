"""The capture engine inside the worker: the audio callback, the ring, the writer.

The callback (the audio thread) only copies the block into a preallocated ring
slot and counts; it never allocates a buffer, takes a lock, touches a file or
raises. A writer thread drains the ring: one ``ProgressiveWav`` per armed
channel, a flush (audio synced, header rewritten, synced) every
``flush_seconds`` of audio, peaks for the level meters, and the next numbered
file when one reaches the WAV size limit.

If the writer falls behind by the whole ring (``ring_seconds``, 20 s by
default: a disk that stalls that long), the callback drops blocks; the writer
then writes the same number of frames of silence so every channel stays in
sync with the recording clock, and reports a ``dropout``. A host input
overflow (audio lost before it reached the callback) is counted and reported
with its position; its length is unknown, so nothing is inserted.

**Armed (pre-roll, WP12c).** An armed capture listens without a take: the writer
keeps the last ``preroll_seconds`` of audio in memory (``PreRoll``) and writes
no file at all. ``begin`` (Record) hands the writer the take's folder, name and
channel names; it opens the files, writes the buffered audio first and goes on
as a normal capture, so the take starts that many seconds before Record was
pressed. Stopping while still armed leaves nothing on disk and the buffer is
gone with the process.
"""

from __future__ import annotations

import contextlib
import errno
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

from kuulas_recorder import names as naming
from kuulas_recorder.sources import AudioSource
from kuulas_recorder.wavfile import MAX_DATA_BYTES, ProgressiveWav, float_to_pcm24

Report = Callable[[dict], None]

# How long without a callback before the device counts as lost. CoreAudio
# delivers a block every ~21 ms at 1024 frames; a second of silence from the
# driver means the device went away (unplugged, or the driver restarted).
LOST_AFTER_S = 1.0
# The first block may take longer: opening a USB interface can take a while.
FIRST_BLOCK_TIMEOUT_S = 5.0


class Ring:
    """Single-producer, single-consumer ring of fixed-size blocks.

    ``written`` is only advanced by the callback and ``read`` only by the
    writer; under the GIL each is a plain int store, so no lock is needed.
    """

    def __init__(self, slots: int, blocksize: int, channels: int):
        self.slots = slots
        self.blocksize = blocksize
        self.buf = np.zeros((slots, blocksize, channels), np.float32)
        self.frames = np.zeros(slots, np.int64)
        self.t_ns = np.zeros(slots, np.int64)  # monotonic time the block arrived
        self.silence_before = np.zeros(slots, np.int64)
        self.overflow = np.zeros(slots, np.bool_)
        self.written = 0
        self.read = 0
        self.callbacks = 0
        self.overflows = 0
        self.dropped_frames = 0
        self.last_ns = 0
        self._pending_silence = 0

    def push(self, indata: np.ndarray, frames: int, overflow: bool) -> None:
        """The audio callback's whole job. Never raises for a full ring."""
        now = time.monotonic_ns()
        self.callbacks += 1
        self.last_ns = now
        if overflow:
            self.overflows += 1
        if self.written - self.read >= self.slots or frames > self.blocksize:
            self._pending_silence += frames
            self.dropped_frames += frames
            return
        s = self.written % self.slots
        self.buf[s, :frames] = indata[:frames]
        self.frames[s] = frames
        self.t_ns[s] = now
        self.overflow[s] = overflow
        self.silence_before[s] = self._pending_silence
        self._pending_silence = 0
        self.written += 1

    def pending(self) -> int:
        return self.written - self.read


class PreRoll:
    """The last ``limit`` frames of audio, in memory, as whole blocks.

    Memory is bounded: blocks older than ``limit`` frames are dropped as new ones
    come, so the buffer never holds more than ``limit`` plus one block.
    """

    def __init__(self, limit: int):
        self.limit = max(0, limit)
        self.frames = 0
        self._blocks: deque[tuple[np.ndarray, int]] = deque()

    def add(self, block: np.ndarray, t_ns: int) -> None:
        """``block``: frames x channels, a copy this buffer may keep; ``t_ns``: the
        monotonic time the block arrived (the end of its audio)."""
        if self.limit == 0 or not len(block):
            return
        self._blocks.append((block, t_ns))
        self.frames += len(block)
        while self._blocks and self.frames - len(self._blocks[0][0]) >= self.limit:
            self.frames -= len(self._blocks.popleft()[0])

    def drain(self) -> tuple[np.ndarray | None, int]:
        """The last ``limit`` frames (or all there are) and the arrival time of the
        newest block; the buffer is emptied."""
        if not self._blocks:
            return None, 0
        newest = self._blocks[-1][1]
        audio = np.concatenate([b for b, _ in self._blocks])[-self.limit:]
        self._blocks.clear()
        self.frames = 0
        return audio, newest


class Capture:
    """Record one device's armed channels to progressive WAVs.

    ``channels`` are 1-based device channel numbers (as in Audio MIDI Setup),
    ``names`` the matching file names. ``segment`` is the number of the first
    file set (1, or later after a restart). Everything that happens is passed
    to ``report`` as a small dict; ``report`` must not block.
    """

    def __init__(self, source: AudioSource, *, folder: Path | str | None,
                 take: str | None, channels: list[int], names: list[str],
                 rate: int = 48000, segment: int = 1, report: Report,
                 blocksize: int = 1024, flush_seconds: float = 1.0,
                 ring_seconds: float = 20.0, level_seconds: float = 0.1,
                 max_data_bytes: int = MAX_DATA_BYTES,
                 opener: Callable[..., ProgressiveWav] = ProgressiveWav,
                 poll_seconds: float = 0.005, armed: bool = False,
                 preroll_seconds: float = 0.0):
        if not channels or (not armed and len(channels) != len(names)):
            raise ValueError("one name per armed channel")
        self.source = source
        self.folder = Path(folder) if folder is not None else None
        self.take = take
        self.channels = list(channels)
        self.names = list(names)
        self.cols = [c - 1 for c in self.channels]
        self.rate = rate
        self.segment = segment
        self.report = report
        self.blocksize = blocksize
        self.flush_frames = max(1, round(flush_seconds * rate))
        self.flush_seconds = flush_seconds
        self.level_frames = max(1, round(level_seconds * rate))
        self.max_data_bytes = max_data_bytes
        self.opener = opener
        self.poll_seconds = poll_seconds
        slots = max(4, int(ring_seconds * rate / blocksize) + 1)
        self.ring = Ring(slots, blocksize, max(self.channels))
        self.files: list[ProgressiveWav] = []
        self.segment_frames = 0  # frames in the current segment's files
        self.total_frames = 0  # frames written in all segments of this worker
        self.dropouts = 0
        self.error: tuple[str, str] | None = None
        self.started_ns = 0
        self.first_block_seen = False
        self.lost_reason: str | None = None
        self._stop = threading.Event()
        self._writer: threading.Thread | None = None
        self._since_flush = 0
        self._flushed_at = 0.0
        self._peaks = np.zeros(len(self.cols), np.float32)
        self._since_levels = 0
        self._overflows_reported = 0
        self._closed = False
        # Pre-roll: ``recording`` is False while armed and no take has begun.
        self.recording = not armed
        self._preroll = PreRoll(round(preroll_seconds * rate)) if armed else None
        self._begin: tuple[Path, str, list[str]] | None = None
        self._listening_reported = False

    # --- files ------------------------------------------------------------------

    def _open_segment(self, *, continues: bool = False) -> None:
        """Open one file per channel. ``continues``: the previous segment hit the
        size limit, so this one starts on the very next frame (no gap)."""
        files = []
        try:
            for name in self.names:
                path = self.folder / naming.segment_file(self.take, name, self.segment)
                files.append(self.opener(path, self.rate,
                                         max_data_bytes=self.max_data_bytes))
        except BaseException:
            for f in files:
                f.abandon()
                with contextlib.suppress(OSError):
                    f.path.unlink()  # empty: created a moment ago, no audio in it
            raise
        self.files = files
        self.segment_frames = 0
        self.report({"ev": "opened", "segment": self.segment, "continues": continues,
                     "files": {n: f.path.name for n, f in zip(self.names, files,
                                                               strict=True)}})

    def _close_segment(self) -> None:
        for f in self.files:
            try:
                f.close()
            except OSError as e:
                self._fail(e)
                f.abandon()
        self.report({"ev": "closed", "segment": self.segment,
                     "frames": self._file_frames()})

    def _file_frames(self) -> dict[str, int]:
        """Frames each file's header on disk covers, by channel name."""
        return {n: f.flushed_frames for n, f in zip(self.names, self.files, strict=True)}

    def _flush(self) -> None:
        for f in self.files:
            f.flush()
        self._since_flush = 0
        self._flushed_at = time.monotonic()
        self.report({"ev": "flushed", "segment": self.segment,
                     "frames": self._file_frames(),
                     "overflows": self.ring.overflows,
                     "dropped_frames": self.ring.dropped_frames})

    def _write(self, block: np.ndarray) -> None:
        """Write ``block`` (frames x armed channels), rolling to the next file set
        at the size limit so no frame is lost or split between channels."""
        while len(block):
            room = self.files[0].room_frames()
            if room == 0:
                self._flush()
                self._close_segment()
                self.segment += 1
                self._open_segment(continues=True)
                continue
            part, block = block[:room], block[room:]
            for i, f in enumerate(self.files):
                f.write(float_to_pcm24(part[:, i]))
            n = len(part)
            self.segment_frames += n
            self.total_frames += n
            self._since_flush += n

    def _fail(self, e: OSError) -> None:
        if self.error is None:
            full = e.errno in (errno.ENOSPC, errno.EDQUOT)
            self.error = ("disk_full" if full else "write_failed",
                          f"Writing the take failed: {e.strerror or e}")

    # --- threads ----------------------------------------------------------------

    def _on_lost(self, why: str) -> None:
        if self.lost_reason is None:
            self.lost_reason = why

    def start(self) -> None:
        """Open the device first (so a refused device leaves no files), then the
        files, then let the writer run. Raises ``SourceError`` or ``OSError``."""
        if self.recording:
            self.folder.mkdir(parents=True, exist_ok=True)
        self.started_ns = time.monotonic_ns()
        self.source.start(self.ring.push, self._on_lost)
        try:
            if self.recording:
                self._open_segment()
        except BaseException:
            self.source.stop()
            raise
        self._flushed_at = time.monotonic()
        self._writer = threading.Thread(target=self._run_writer, name="writer",
                                        daemon=True)
        self._writer.start()

    def _run_writer(self) -> None:
        try:
            self._drain_loop()
        except OSError as e:
            self._fail(e)
        except BaseException as e:  # noqa: BLE001 - reported, then the worker exits
            self.error = ("internal", f"The writer stopped: {e!r}")
        if self.error is not None:
            # Make what is on disk as complete as it can be: each header covers
            # every frame that was fully written.
            for f in self.files:
                with contextlib.suppress(OSError):
                    f.flush()
            self.report({"ev": "error", "key": self.error[0], "text": self.error[1]})

    def _drain_loop(self) -> None:
        ring = self.ring
        while True:
            if self._begin is not None and not self.recording:
                self._start_recording()
            if ring.pending():
                self._take_block()
                continue
            if self._stop.is_set():
                return
            if self._since_flush and time.monotonic() - self._flushed_at >= (
                    self.flush_seconds):
                self._flush()
            time.sleep(self.poll_seconds)

    def _take_block(self) -> None:
        ring = self.ring
        s = ring.read % ring.slots
        frames = int(ring.frames[s])
        silence = int(ring.silence_before[s])
        if not self.recording:
            self._listen_block(s, frames, silence)
            return
        if not self.first_block_seen:
            self.first_block_seen = True
            # The block's first frame was captured one block before it arrived.
            start_ns = int(ring.t_ns[s]) - frames * 1_000_000_000 // self.rate
            self.report({"ev": "first_block", "segment": self.segment,
                         "mono_ns": start_ns,
                         "utc_ns": time.time_ns() - (time.monotonic_ns() - start_ns)})
        if silence:
            at = self.total_frames
            self._write(np.zeros((silence, len(self.cols)), np.float32))
            self.dropouts += 1
            self.report({"ev": "dropout", "segment": self.segment, "at": at,
                         "frames": silence})
        if ring.overflow[s] and ring.overflows != self._overflows_reported:
            self._overflows_reported = ring.overflows
            self.report({"ev": "overflow", "segment": self.segment,
                         "at": self.total_frames, "count": ring.overflows})
        block = ring.buf[s, :frames][:, self.cols]  # a copy (fancy index)
        ring.read += 1
        self._write(block)
        self._levels(block)
        if self._since_flush >= self.flush_frames:
            self._flush()

    def _listen_block(self, s: int, frames: int, silence: int) -> None:
        """Armed: the block goes to the pre-roll buffer (and the meters), not to disk."""
        ring = self.ring
        if not self._listening_reported:
            self._listening_reported = True
            self.report({"ev": "listening"})
        t_ns = int(ring.t_ns[s])
        if silence:  # the ring overflowed: keep the buffer on the clock
            self._preroll.add(np.zeros((silence, len(self.cols)), np.float32), t_ns)
        block = ring.buf[s, :frames][:, self.cols]  # a copy (fancy index)
        ring.read += 1
        self._preroll.add(block, t_ns)
        self._levels(block)

    def begin(self, folder: Path | str, take: str, names: list[str]) -> None:
        """Record (armed captures): the writer opens the files and writes the buffered
        audio first. Returns at once; a failure is reported as an ``error`` event."""
        if self.recording or self._preroll is None:
            raise ValueError("begin is for an armed capture that has not begun")
        if len(names) != len(self.cols):
            raise ValueError("one name per armed channel")
        self._begin = (Path(folder), take, list(names))

    def buffered_frames(self) -> int:
        """Frames the pre-roll buffer holds now (0 once recording)."""
        return self._preroll.frames if self._preroll is not None else 0

    def _start_recording(self) -> None:
        """The writer thread's half of ``begin``: open the files, write the pre-roll."""
        self.folder, self.take, self.names = self._begin
        self._begin = None
        self.folder.mkdir(parents=True, exist_ok=True)
        self._open_segment()
        audio, newest_ns = self._preroll.drain()
        self._preroll = None
        self.recording = True
        self._flushed_at = time.monotonic()
        frames = 0 if audio is None else len(audio)
        self.report({"ev": "preroll", "frames": frames})
        if not frames:
            return  # the first block to come starts the take, as without pre-roll
        # The take's frame 0 is the oldest buffered frame; blocks are contiguous.
        start_ns = newest_ns - frames * 1_000_000_000 // self.rate
        self.first_block_seen = True
        self.report({"ev": "first_block", "segment": self.segment, "mono_ns": start_ns,
                     "utc_ns": time.time_ns() - (time.monotonic_ns() - start_ns)})
        self._write(audio)

    def _levels(self, block: np.ndarray) -> None:
        if len(block):
            np.maximum(self._peaks, np.abs(block).max(axis=0), out=self._peaks)
        self._since_levels += len(block)
        if self._since_levels >= self.level_frames:
            self.report({"ev": "levels", "peaks": [float(p) for p in self._peaks]})
            self._peaks[:] = 0
            self._since_levels = 0

    # --- control ----------------------------------------------------------------

    def poll(self, now_ns: int | None = None) -> str | None:
        """Called by the worker every few tens of ms: ``"device_lost"``, ``"error"``
        or None. The device counts as lost when the source says so or when no
        callback came for ``LOST_AFTER_S``."""
        if self.error is not None:
            return "error"
        if self.lost_reason is not None:
            return "device_lost"
        now = time.monotonic_ns() if now_ns is None else now_ns
        last = self.ring.last_ns
        if last == 0:
            if now - self.started_ns > FIRST_BLOCK_TIMEOUT_S * 1e9:
                self.lost_reason = "no_audio"
                return "device_lost"
        elif now - last > LOST_AFTER_S * 1e9:
            self.lost_reason = "callbacks_stopped"
            return "device_lost"
        return None

    def wait_drained(self, timeout: float = 10.0) -> bool:
        """Wait until the writer has taken every block (tests)."""
        end = time.monotonic() + timeout
        while self.ring.pending() and self.error is None:
            if time.monotonic() > end:
                return False
            time.sleep(0.001)
        return True

    def stop(self) -> None:
        """Stop the device, write every block already captured, flush, close.
        Safe to call twice and after an error."""
        if self._closed:
            return
        self._closed = True
        self.source.stop()
        self._stop.set()
        if self._writer is not None:
            self._writer.join()
        if not self.recording:
            return  # armed and never begun: nothing was written, nothing to close
        if self.error is None:
            try:
                self._flush()
            except OSError as e:
                self._fail(e)
        self._close_segment()
