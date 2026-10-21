"""A clipboard preview as one more voice in the running playback (owner,
2026-10-21: "the clipboard should MIX INTO the playback, not TAKE OVER").

``PreviewVoice`` holds the temporary project, its own position and, when the device
runs at another rate than the project, its own resampler. The audio callback asks it for
a block and sums that into the timeline's block; the voice reads media only from the
engine's read-ahead cache (``_SafeStore``), so a block never touches the disk.

Everything here runs on the audio thread after the control side has built the voice
(resampler included) and warmed the cache; ``render`` takes no lock and allocates only
the block. The control side reads the plain fields ``heard`` and ``done``.
"""

from __future__ import annotations

import math

import numpy as np
import soxr

from . import mixer
from .model import Project


class PreviewVoice:
    def __init__(self, project: Project, store: mixer.Store, device_rate: int, *,
                 limit: bool, until: int | None = None, clock_now: float = 0.0):
        self.project = project
        self.store = store
        self.rate = project.rate
        self.device_rate = int(device_rate)
        self.limit = limit
        self.end = project.length if until is None else max(0, min(int(until),
                                                                    project.length))
        self.pos = 0  # the next project frame to mix
        self.done = False
        #: (project frames heard so far, clock time of that reading): replaced whole
        self.heard: tuple[int, float] = (0, clock_now)
        self._emitted = 0  # device frames handed out
        self._fifo = np.zeros((0, 2), dtype=np.float32)
        self._flushed = False
        self._resampler = None if self.device_rate == self.rate else soxr.ResampleStream(
            self.rate, self.device_rate, 2, dtype="float32", quality="HQ")

    def windows(self, seconds: float) -> tuple[int, int]:
        """The project frames wanted in the cache for the next ``seconds``."""
        return self.pos, min(self.end, self.pos + round(seconds * self.rate))

    def render(self, frames: int, now: float) -> np.ndarray:
        """``(frames, 2)`` float32 at the device rate: the next block of the voice,
        zero-padded when it runs out (then ``done`` is set)."""
        out = np.zeros((frames, 2), dtype=np.float32)
        ratio = self.rate / self.device_rate
        chunks = [self._fifo]
        have = len(self._fifo)
        while have < frames and not self._flushed:
            n = min(max(1, math.ceil(frames * ratio)), max(0, self.end - self.pos))
            if n > 0:
                block = mixer.mix(self.project, self.store, self.pos, n)
                self.pos += n
                y = (block.T if self._resampler is None else
                     self._resampler.resample_chunk(np.ascontiguousarray(block.T)))
                chunks.append(y)
                have += len(y)
            if self.pos >= self.end:
                if self._resampler is not None:
                    tail = self._resampler.resample_chunk(
                        np.zeros((0, 2), dtype=np.float32), last=True)
                    chunks.append(tail)
                    have += len(tail)
                self._flushed = True
        queued = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        take = min(frames, len(queued))
        out[:take] = queued[:take]
        self._fifo = queued[take:]
        self._emitted += take
        self.heard = (self._emitted * self.rate // self.device_rate, now)
        if self._flushed and len(self._fifo) == 0:
            self.done = True
        return out
