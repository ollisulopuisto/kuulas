"""What one ``play`` plays: the programme minus a skip list (WP18, WP26).

``Engine.play(at, until, skip=...)`` plays the programme from ``at`` but
jumps over every skipped range ``[a, b)``. A ``PlayPlan`` turns that into the
*played stretches* ("pieces") laid end to end on a *played timeline*, and
renders any window of that timeline from ``mixer.mix``. The engine then reads
the played timeline forwards, backwards or resampled (tape rate) and never
needs to know about skips; the plan maps a played frame back to the
programme frame for the playhead.

**Joins are crossfaded, never cut.** At each join the outgoing piece runs on
for ``h`` frames into the skipped audio while fading out by cos, and the
incoming piece starts ``h`` frames early (also skipped audio) fading in by
sin: a centred equal-power crossfade of ``2h`` frames, ``XFADE_S`` long, or
half the shorter neighbouring piece if that is less. Centring it keeps the
played length exactly the sum of the pieces, so the playhead arithmetic stays
exact. Equal power, not the mixer's equal-gain clip crossfade: the two sides
of a skip are unrelated audio, whose powers add. The very start and end of
playback are hard, as plain ``play`` is today.

Everything here is computed when the plan is made (on the control side);
``read`` only mixes, slices and multiplies, so it is fit for the audio
thread.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable

import numpy as np

from . import mixer
from .messages import KuulasError

#: The crossfade across a skipped range: 15 ms, inside the 10-20 ms that
#: hides the join without smearing the words on either side of it.
XFADE_S = 0.015


class PlaybackRequestError(KuulasError):
    """A play request the engine cannot honour as asked: a malformed skip
    list, a speed out of range, or pitch-kept fast playback (not built)."""


def check_skip(skip: object) -> tuple[tuple[int, int], ...]:
    """``skip`` as a tuple of ``(a, b)`` frame pairs with ``0 <= a <= b``.

    Raises ``PlaybackRequestError`` for anything else: the API and the
    engine both use this, so a bad list is refused before anything plays.
    """
    if skip is None:
        return ()
    if isinstance(skip, (str, bytes)) or not isinstance(skip, Iterable):
        raise PlaybackRequestError("error.engine.bad_skip", item=str(skip)[:40])
    out = []
    for item in skip:
        try:
            a, b = item
        except (TypeError, ValueError):
            raise PlaybackRequestError("error.engine.bad_skip",
                                       item=str(item)[:40]) from None
        ok = all(isinstance(x, (int, np.integer)) and not isinstance(x, bool)
                 for x in (a, b))
        if not ok or not 0 <= a <= b:
            raise PlaybackRequestError("error.engine.bad_skip", item=str(item)[:40])
        out.append((int(a), int(b)))
    return tuple(out)


def normalise_skip(skip: object, lo: int, hi: int) -> tuple[tuple[int, int], ...]:
    """The skip list sorted, overlapping and touching ranges merged, clipped
    to ``[lo, hi)``; empty ranges dropped."""
    ranges = sorted((max(lo, a), min(hi, b)) for a, b in check_skip(skip))
    merged: list[list[int]] = []
    for a, b in ranges:
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return tuple((a, b) for a, b in merged)


def _equal_power(h: int) -> tuple[np.ndarray, np.ndarray]:
    """Fade-out (cos) and fade-in (sin) over ``2h`` frames, sample-centred,
    so cos² + sin² = 1 on every frame."""
    theta = (np.arange(2 * h, dtype=np.float64) + 0.5) / (2 * h) * (math.pi / 2)
    return (np.cos(theta).astype(np.float32), np.sin(theta).astype(np.float32))


class PlayPlan:
    """The pieces of ``[lo, hi)`` left by ``skip`` (already normalised).

    ``open_end``: playback runs to the end of the project, whatever its
    length when a block is mixed (an edit while playing can move it), so the
    last piece, if it reaches ``hi``, follows the project length.
    ``capped`` (default: ``open_end``): nothing past the project's end is
    played, however long it is when a block is mixed. Without either, the
    pieces are fixed (backward play reads them from the end).
    """

    def __init__(self, lo: int, hi: int, skip: tuple[tuple[int, int], ...], *,
                 rate: int, open_end: bool, capped: bool | None = None):
        self.lo, self.hi, self.open_end = int(lo), int(hi), open_end
        self.capped = open_end if capped is None else capped
        self.skip = skip
        pieces, at = [], self.lo
        for a, b in skip:
            if a > at:
                pieces.append((at, a))
            at = max(at, b)
        if self.hi > at:
            pieces.append((at, self.hi))
        self.pieces: tuple[tuple[int, int], ...] = tuple(pieces)
        #: Does the last piece end with the project (open end)?
        self._last_open = open_end and bool(pieces) and pieces[-1][1] == self.hi
        starts, t = [], 0
        for a, b in pieces:
            starts.append(t)
            t += b - a
        #: Where each piece starts on the played timeline.
        self.vstarts: tuple[int, ...] = tuple(starts)
        cap = round(XFADE_S * rate / 2)
        widths = [0]
        for k in range(1, len(pieces)):
            before = pieces[k - 1][1] - pieces[k - 1][0]
            after = pieces[k][1] - pieces[k][0]
            widths.append(min(cap, before // 2, after // 2))
        #: Half-width of the crossfade into each piece (0: none).
        self.half_widths: tuple[int, ...] = tuple(widths)
        self._fades = [_equal_power(h) if h else None for h in widths]

    def _end(self, k: int, length: int) -> int:
        """Where piece ``k`` ends in programme frames, for this project length."""
        a, b = self.pieces[k]
        if k == len(self.pieces) - 1 and self._last_open:
            return max(a, length)
        return min(b, max(a, length)) if self.capped else b

    def _last(self, length: int) -> int:
        """Index of the last piece that has anything to play, or -1."""
        k = len(self.pieces) - 1
        if self.capped:
            while k >= 0 and self.pieces[k][0] >= length:
                k -= 1
        return k

    def length(self, length: int) -> int:
        """Frames on the played timeline, for a project ``length`` long."""
        k = self._last(length)
        if k < 0:
            return 0
        return self.vstarts[k] + self._end(k, length) - self.pieces[k][0]

    def final(self, length: int) -> int:
        """The programme frame playback ends on."""
        if self.open_end:
            return max(self.lo, length)
        return max(self.lo, min(self.hi, length)) if self.capped else self.hi

    def position(self, v: int, length: int) -> int:
        """The programme frame at played frame ``v``: inside a piece, its own
        frame; at or after the end, ``final``. The playhead jumps at the
        middle of each crossfade."""
        if v >= self.length(length):
            return self.final(length)
        k = max(0, bisect.bisect_right(self.vstarts, v) - 1)
        return self.pieces[k][0] + max(0, v) - self.vstarts[k]

    def read(self, project, store, v: int, n: int) -> np.ndarray:
        """``(2, n)`` float32: played frames ``[v, v + n)``, crossfaded."""
        total = self.length(project.length)
        last = self._last(project.length)
        if len(self.pieces) == 1 and last == 0:  # no skip: plain playback
            a = self.pieces[0][0]
            return mixer.mix(project, store, a + v, n)
        out = np.zeros((2, n), dtype=np.float32)
        end = min(v + n, total)
        first = max(0, bisect.bisect_right(self.vstarts, v) - 1)
        if first and v < self.vstarts[first] + self.half_widths[first]:
            first -= 1  # the piece before still fades out under this one
        for k in range(first, last + 1):
            vs = self.vstarts[k]
            h_in = self.half_widths[k]
            if vs - h_in >= end:
                break
            a, b = self.pieces[k]
            h_out = self.half_widths[k + 1] if k < last else 0
            ve = vs + (b - a)
            lo, hi = max(v, vs - h_in), min(end, ve + h_out)
            if hi <= lo:
                continue
            block = mixer.mix(project, store, a + lo - vs, hi - lo)
            if h_in:
                self._apply(block, self._fades[k][1], lo, hi, vs - h_in)
            if h_out:
                self._apply(block, self._fades[k + 1][0], lo, hi, ve - h_out)
            out[:, lo - v:hi - v] += block
        return out

    @staticmethod
    def _apply(block: np.ndarray, gain: np.ndarray, lo: int, hi: int, at: int) -> None:
        """Multiply the part of ``block`` (played frames ``[lo, hi)``) that
        meets ``gain`` (played frames ``[at, at + len(gain))``)."""
        x0, x1 = max(lo, at), min(hi, at + len(gain))
        if x1 > x0:
            block[:, x0 - lo:x1 - lo] *= gain[x0 - at:x1 - at]
