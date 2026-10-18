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

**A loop is a backward skip (WP50).** With ``loop=(start, end)`` the pieces of
``[start, end)`` minus the skip list repeat for ever: the played timeline is
endless and the wrap from the last piece back to the first is a join like any
other, with the same equal-power crossfade, so a loop over a cut plays what
the edit sounds like. A lead-in (``lo`` outside the loop, or inside it) is a
*head* of pieces played once before the cycle. ``then`` builds the plan that
goes on from a later wrap with another loop, or none, with the played
timeline up to that wrap unchanged: what the audio thread has already mixed
stays true.

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
#: The shortest loop worth wrapping (after the skips), 50 ms: every wrap
#: costs a mix and a crossfade, so a loop of a few frames would be a buzz and
#: a busy callback.
MIN_LOOP_S = 0.05
#: The length of an endless played timeline: far past any real session.
ENDLESS = 2**62


class PlaybackRequestError(KuulasError):
    """A play request the engine cannot honour as asked: a malformed skip
    list or loop, a speed out of range, or pitch-kept fast playback (not
    built)."""


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


def _pieces_of(lo: int, hi: int,
               skip: tuple[tuple[int, int], ...]) -> list[tuple[int, int]]:
    """The played stretches of ``[lo, hi)`` minus ``skip`` (normalised)."""
    pieces, at = [], lo
    for a, b in skip:
        if a > at:
            pieces.append((at, a))
        at = max(at, b)
    if hi > at:
        pieces.append((at, hi))
    return pieces


def check_loop(loop: object, skip: object, rate: int) -> tuple[int, int]:
    """``loop`` as a ``(start, end)`` pair of frames, ``0 <= start < end``,
    with at least ``MIN_LOOP_S`` left of it once ``skip`` is taken out.

    Raises ``PlaybackRequestError`` for anything else, before anything plays.
    """
    try:
        a, b = loop  # type: ignore[misc]
    except (TypeError, ValueError):
        raise PlaybackRequestError("error.engine.bad_loop", loop=str(loop)[:40]) from None
    ok = all(isinstance(x, (int, np.integer)) and not isinstance(x, bool) for x in (a, b))
    if ok:
        a, b = int(a), int(b)
        kept = sum(y - x for x, y in _pieces_of(a, b, normalise_skip(skip, a, b)))
        ok = 0 <= a < b and kept >= MIN_LOOP_S * rate
    if not ok:
        raise PlaybackRequestError("error.engine.bad_loop", loop=str(loop)[:40])
    return a, b


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

    ``loop=(start, end)``: the pieces of the loop repeat for ever (``skip``
    is then the whole skip list, not yet clipped); ``lo`` is where playing
    starts, a lead-in to the loop's end unless it is the loop's start or
    past its end. ``prefix``: pieces already laid before the rest (``then``).
    """

    def __init__(self, lo: int, hi: int, skip: tuple[tuple[int, int], ...], *,
                 rate: int, open_end: bool, capped: bool | None = None,
                 loop: tuple[int, int] | None = None,
                 prefix: tuple[tuple[int, int], ...] | None = None):
        self.lo, self.hi, self.open_end = int(lo), int(hi), open_end
        self.capped = open_end if capped is None else capped
        self.skip = skip
        self.loop = loop
        self._rate = rate
        #: Where the cycle starts among the pieces (None: no loop).
        self.cycle_at: int | None = None
        if loop is None:
            pieces = list(prefix or ()) + _pieces_of(self.lo, self.hi, skip)
        else:
            start, end = loop
            cycle = _pieces_of(start, end, normalise_skip(skip, start, end))
            if not cycle:
                raise PlaybackRequestError("error.engine.bad_loop", loop=str(loop))
            if prefix is not None:
                lead = list(prefix)
            elif self.lo != start and self.lo < end:
                lead = _pieces_of(self.lo, end, normalise_skip(skip, self.lo, end))
            else:
                lead = []
            pieces = lead + cycle
            self.cycle_at = len(lead)
            self.capped = False
        self.pieces: tuple[tuple[int, int], ...] = tuple(pieces)
        #: Does the last piece end with the project (open end)?
        self._last_open = (open_end and loop is None and bool(pieces)
                           and pieces[-1][1] == self.hi)
        starts, t = [], 0
        for a, b in pieces:
            starts.append(t)
            t += b - a
        #: Where each piece starts on the played timeline.
        self.vstarts: tuple[int, ...] = tuple(starts)
        self._total = t
        cap = round(XFADE_S * rate / 2)
        curves: dict[int, tuple[np.ndarray, np.ndarray] | None] = {0: None}

        def curve(h: int):
            if h not in curves:  # one pair of curves per width, not per join
                curves[h] = _equal_power(h)
            return curves[h]

        widths = [0]
        for k in range(1, len(pieces)):
            before = pieces[k - 1][1] - pieces[k - 1][0]
            after = pieces[k][1] - pieces[k][0]
            # Pieces that run on into each other need no join: a crossfade of
            # the same audio against itself would swell by 3 dB.
            touching = pieces[k - 1][1] == pieces[k][0]
            widths.append(0 if touching else min(cap, before // 2, after // 2))
        #: Half-width of the crossfade into each piece (0: none).
        self.half_widths: tuple[int, ...] = tuple(widths)
        self._fades = [curve(h) for h in widths]
        #: A loop's join from its last piece back into its first: the
        #: half-width and the (fade-out, fade-in) curves.
        self.wrap_half = 0
        self._wrap_fades = None
        #: Played frames where the cycle starts, and how long it is.
        self._v0 = self._period = 0
        #: Set by ``then``: the half-width of the join where it takes over.
        self.splice_half = 0
        if self.cycle_at is not None:
            first, last = pieces[self.cycle_at], pieces[-1]
            self.wrap_half = min(cap, (last[1] - last[0]) // 2,
                                 (first[1] - first[0]) // 2)
            self._wrap_fades = curve(self.wrap_half)
            self._v0 = starts[self.cycle_at]
            self._period = t - self._v0

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
        if self.cycle_at is not None:
            return ENDLESS
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
        middle of each crossfade, and back at each wrap of a loop."""
        if v >= self.length(length):
            return self.final(length)
        if self.cycle_at is not None and v >= self._v0:
            v = self._v0 + (v - self._v0) % self._period
        k = max(0, bisect.bisect_right(self.vstarts, v) - 1)
        return self.pieces[k][0] + max(0, v) - self.vstarts[k]

    def wrap_at_or_after(self, v: int) -> int:
        """The first played frame at or after ``v`` where the cycle begins
        (again): the start of its first pass, or a later wrap."""
        if v <= self._v0:
            return self._v0
        return self._v0 + -(-(v - self._v0) // self._period) * self._period

    def then(self, w: int, *, loop: tuple[int, int] | None, skip: object, hi: int,
             open_end: bool, capped: bool) -> PlayPlan:
        """A plan that plays as this one up to played frame ``w`` (one
        ``wrap_at_or_after`` gave) and from there loops ``loop`` or, without
        one, goes on from this loop's end to ``hi``. The join at ``w`` is
        like any other; ``splice_half`` says how wide it is."""
        if self.cycle_at is None:
            raise ValueError("then() is for a looping plan")
        passes = (w - self._v0) // self._period
        prefix = self.pieces[:self.cycle_at] + self.pieces[self.cycle_at:] * passes
        if loop is not None:
            plan = PlayPlan(0, hi, skip, rate=self._rate, open_end=False,  # type: ignore[arg-type]
                            loop=loop, prefix=prefix)
        else:
            lo = self.loop[1] if self.loop is not None else 0
            plan = PlayPlan(lo, hi, normalise_skip(skip, lo, hi), rate=self._rate,
                            open_end=open_end, capped=capped, prefix=prefix)
        if len(prefix) < len(plan.pieces):
            plan.splice_half = plan.half_widths[len(prefix)]
        return plan

    def read(self, project, store, v: int, n: int) -> np.ndarray:
        """``(2, n)`` float32: played frames ``[v, v + n)``, crossfaded."""
        if self.cycle_at is None:
            return self._read_pieces(project, store, v, n,
                                     self.length(project.length), False)
        out = np.zeros((2, n), dtype=np.float32)
        v0, period, total, h = self._v0, self._period, self._total, self.wrap_half
        pos, end = v, v + n
        while pos < end:
            if pos < v0:
                u, m, later = pos, min(end, v0) - pos, False
            else:
                off = (pos - v0) % period
                u, m, later = v0 + off, min(end - pos, period - off), pos >= v0 + period
            at = pos - v
            out[:, at:at + m] = self._read_pieces(project, store, u, m, total, later)
            if h and u >= v0:
                fade_out, fade_in = self._wrap_fades
                if later and u < v0 + h:
                    # The last piece runs on into the cycle's first frames,
                    # fading out under it.
                    cnt = min(u + m, v0 + h) - u
                    block = mixer.mix(project, store, self.pieces[-1][1] + u - v0, cnt)
                    block *= fade_out[h + u - v0:h + u - v0 + cnt]
                    out[:, at:at + cnt] += block
                if u + m > total - h:
                    # The first piece starts early, fading in under the end
                    # of the pass.
                    lo = max(u, total - h)
                    cnt = u + m - lo
                    block = self._mix_from(
                        project, store,
                        self.pieces[self.cycle_at][0] - h + lo - (total - h), cnt)
                    block *= fade_in[lo - (total - h):lo - (total - h) + cnt]
                    out[:, at + lo - u:at + lo - u + cnt] += block
            pos += m
        return out

    @staticmethod
    def _mix_from(project, store, start: int, n: int) -> np.ndarray:
        """``mixer.mix`` from ``start``, which may be before the project's
        start: that part is silence."""
        if start >= 0:
            return mixer.mix(project, store, start, n)
        out = np.zeros((2, n), dtype=np.float32)
        gap = min(n, -start)
        if n > gap:
            out[:, gap:] = mixer.mix(project, store, 0, n - gap)
        return out

    def _read_pieces(self, project, store, v: int, n: int, total: int,
                     later: bool) -> np.ndarray:
        """Played frames ``[v, v + n)`` of the pieces laid end to end, up to
        ``total``. ``later``: in a repeat of the cycle, whose first piece is
        entered from the wrap, not from the lead-in."""
        looping = self.cycle_at is not None
        last = len(self.pieces) - 1 if looping else self._last(project.length)
        if len(self.pieces) == 1 and last == 0 and not looping:  # plain playback
            a = self.pieces[0][0]
            return mixer.mix(project, store, a + v, n)
        out = np.zeros((2, n), dtype=np.float32)
        end = min(v + n, total)
        first = max(0, bisect.bisect_right(self.vstarts, v) - 1)
        if (first and v < self.vstarts[first] + self.half_widths[first]
                and not (later and first == self.cycle_at)):
            first -= 1  # the piece before still fades out under this one
        for k in range(first, last + 1):
            vs = self.vstarts[k]
            if later and k == self.cycle_at:
                h_in, fade_in = self.wrap_half, self._wrap_fades
            else:
                h_in, fade_in = self.half_widths[k], self._fades[k]
            if vs - h_in >= end:
                break
            a, b = self.pieces[k]
            if k < last:
                h_out, fade_out = self.half_widths[k + 1], self._fades[k + 1]
            elif looping:
                h_out, fade_out = self.wrap_half, self._wrap_fades
            else:
                h_out, fade_out = 0, None
            ve = vs + (b - a)
            lo, hi = max(v, vs - h_in), min(end, ve + h_out)
            if hi <= lo:
                continue
            block = mixer.mix(project, store, a + lo - vs, hi - lo)
            if h_in:
                self._apply(block, fade_in[1], lo, hi, vs - h_in)
            if h_out:
                self._apply(block, fade_out[0], lo, hi, ve - h_out)
            out[:, lo - v:hi - v] += block
        return out

    @staticmethod
    def _apply(block: np.ndarray, gain: np.ndarray, lo: int, hi: int, at: int) -> None:
        """Multiply the part of ``block`` (played frames ``[lo, hi)``) that
        meets ``gain`` (played frames ``[at, at + len(gain))``)."""
        x0, x1 = max(lo, at), min(hi, at + len(gain))
        if x1 > x0:
            block[:, x0 - lo:x1 - lo] *= gain[x0 - at:x1 - at]
