"""Grain renderer for fast shuttle (WP26): speeds above 2x.

Tape-style resampling makes speech unintelligible above 2x. Here the mix is
played in short grains at normal pitch: each grain is ``GRAIN_S`` long, and
the read position jumps ahead (or back) by ``GRAIN_S * |speed|`` between
grains, so the programme position still moves at ``speed``. Grains overlap by
``XFADE_S`` with a raised-cosine fade, so the joins do not click.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

GRAIN_S = 0.060
"""Length of one played grain."""

XFADE_S = 0.010
"""Crossfade between neighbouring grains (shorter than half a grain)."""

MIN_SPEED = 2.0
"""The grain renderer serves |speed| above this; tape resampling serves less."""

Read = Callable[[int, int], np.ndarray]


class GrainStream:
    """Grains one unit at a time, with the crossfade carried between units.

    ``unit()`` returns ``step`` frames (a grain minus its crossfade) and moves
    ``position`` by ``step * speed`` programme frames. The last ``xfade``
    frames of each grain are held back and faded into the next one.
    """

    def __init__(self, read: Read, *, start: float, speed: float, rate: int,
                 fade: bool = True):
        if not np.isfinite(speed) or abs(speed) < 1.0 + 1e-9:
            msg = f"grain speed must be at least 1x in size, got {speed}"
            raise ValueError(msg)
        self.read, self.speed, self.position = read, float(speed), float(start)
        self.grain = max(2, round(GRAIN_S * rate))
        self.xfade = min(round(XFADE_S * rate), self.grain // 2 - 1) if fade else 0
        self.step = self.grain - self.xfade
        x = self.xfade
        self._ramp = ((0.5 - 0.5 * np.cos(np.pi * (np.arange(x) + 0.5) / x))
                      .astype(np.float32)[:, None] if x else None)
        self._tail: np.ndarray | None = None

    def unit(self) -> np.ndarray:
        first = round(self.position)
        if self.speed < 0:
            first -= self.grain            # a backward grain ends at the position
        block = np.array(self.read(first, self.grain), dtype=np.float32)
        x = self.xfade
        if self._tail is not None and x:
            block[:x] = self._tail * (1.0 - self._ramp) + block[:x] * self._ramp
        self._tail = block[self.step:].copy() if x else None
        self.position += self.step * self.speed
        return block[:self.step]


def render_grains(read: Read, *, start: int, speed: float, frames: int, rate: int,
                  fade: bool = True) -> tuple[np.ndarray, float]:
    """Render ``frames`` output frames of grains from ``read(first, count)``.

    ``read`` returns a ``(count, 2)`` float32 block of the finished mix (zeros
    outside the programme). Returns ``(audio, end)``: the audio and the
    programme position after it, ``frames * speed`` away from ``start``.
    Grains always play forward; a negative speed only moves the read position
    back between them.
    """
    if speed == 0.0:
        msg = "grain speed must not be zero"
        raise ValueError(msg)
    stream = GrainStream(read, start=start, speed=speed, rate=rate, fade=fade)
    parts, have = [], 0
    while have < frames:
        u = stream.unit()
        parts.append(u)
        have += len(u)
    return np.concatenate(parts)[:frames], float(start) + frames * speed
