"""Speech faster or slower with the pitch kept: streaming WSOLA (WP26).

**Prior art, and why this is written here.** Rubber Band (through
pedalboard's ``time_stretch``) renders a whole buffer at one fixed ratio, and
the plan was to pre-render 2 s chunks of it. The owner wants the speed
*stepless* and changeable while playing; a chunk renderer can only change
speed at a chunk edge, 2 s late, and has to be crossfaded. audiotsm has a
streaming WSOLA with ``set_speed``, but it is a new dependency that pulls its
input in its own buffer layout, and the engine already owns the mix. About a
hundred lines of numpy do the same job and keep the callback cost known.

**How it works** (waveform-similarity overlap-add). Output is built in hops of
``HOP`` frames (20 ms). Each hop adds a Hann-windowed grain of two hops (40 ms)
to the tail of the previous grain; the windows sum to exactly 1, so a steady
tone keeps its level. Where in the input the grain comes from advances by
``HOP * rate`` per hop, so the programme runs ``rate`` times faster. Taking
grains from the input at their natural speed is what keeps the pitch. The
grain's exact start is searched within +-``SEARCH`` (8 ms) of that nominal
place for the position whose first hop best continues the previous grain
(normalised correlation, coarsely on a 4x decimated mono mix, then refined at
the full rate), so the joins are in phase and do not click or flange.

**Stepless.** ``rate`` is read at every hop, so it can be changed while
playing: the next grain just starts further along; nothing is restarted and
no join is different from any other.

**Cost.** One hop is one correlation over about 100 candidates on 240
decimated samples plus 9 refinements, and a window multiply: well under a
millisecond, measured in ``tests/test_stretch.py``. The input is pulled by a
``fetch(first, count)`` callable (the engine's mix of the played timeline) a
hop at a time, so a block costs about what plain playback costs.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

#: A hop (and the overlap) in seconds: a grain is two hops. 20 ms keeps
#: several pitch periods of a low male voice (8 ms at 125 Hz) in every overlap
#: while staying short enough that speech at 2x is not smeared.
HOP_S = 0.020
#: How far from the nominal place a grain may start, seconds: one period of
#: the lowest voices plus margin.
SEARCH_S = 0.008
#: The coarse search runs on every ``DECIMATE``-th sample (mean of each group).
DECIMATE = 4
#: The speeds ``set_speed`` accepts (the refinement and windows work in all).
MIN_RATE = 0.5
MAX_RATE = 3.0


class Stretcher:
    """Pulls input through ``fetch(first, count) -> (2, count) float32`` and
    gives out ``(hop, 2)`` float32 blocks, the programme at ``rate`` times
    its speed. ``length`` is the input's length in frames; the stream ends
    when the nominal position passes it."""

    def __init__(self, fetch: Callable[[int, int], np.ndarray], length: int,
                 rate_hz: int, speed: float = 1.0):
        self.fetch = fetch
        self.length = int(length)
        self.hop = max(16, round(HOP_S * rate_hz))
        self.search = max(DECIMATE, round(SEARCH_S * rate_hz))
        self.speed = float(speed)
        n = np.arange(2 * self.hop, dtype=np.float64)
        #: Periodic Hann: window[n] + window[n + hop] == 1.
        self._window = (0.5 - 0.5 * np.cos(2 * math.pi * n / (2 * self.hop))).astype(
            np.float32)
        #: Nominal input position of the next grain (frames, fractional).
        self._pos = 0.0
        #: Input frames [base, base + len) held from the last fetches.
        self._base = 0
        self._data = np.zeros((2, 0), dtype=np.float32)
        #: What continues the previous grain naturally, and its falling half.
        self._template: np.ndarray | None = None
        self._tail = np.zeros((2, self.hop), dtype=np.float32)
        self._ended = False
        self._draining = False

    @property
    def position(self) -> float:
        """Nominal input frame the next grain is taken from."""
        return self._pos

    @property
    def finished(self) -> bool:
        return self._ended

    def set_speed(self, speed: float) -> None:
        """The speed from the next hop on (any value, any time)."""
        self.speed = min(MAX_RATE, max(MIN_RATE, float(speed)))

    # -- input -------------------------------------------------------------------

    def _input(self, first: int, last: int) -> np.ndarray:
        """Input frames ``[first, last)`` as ``(2, last - first)``; before 0
        and past the length is silence. Only what is not held is fetched."""
        top = self._base + self._data.shape[1]
        if self._data.shape[1] == 0 or first < self._base or first > top:
            self._base, self._data = first, self._get(first, last)
        elif last > top:
            self._data = np.concatenate(
                [self._data, self._get(top, last)], axis=1)
        drop = first - self._base
        if drop > 0:
            self._data = self._data[:, drop:]
            self._base = first
        return self._data[:, :last - first]

    def _get(self, first: int, last: int) -> np.ndarray:
        out = np.zeros((2, last - first), dtype=np.float32)
        lo, hi = max(first, 0), min(last, self.length)
        if hi > lo:
            out[:, lo - first:hi - first] = self.fetch(lo, hi - lo)
        return out

    # -- the search --------------------------------------------------------------

    def _best_start(self, nominal: int, segment: np.ndarray, first: int,
                    template: np.ndarray) -> int:
        """The start in ``[nominal - search, nominal + search]`` whose first
        hop best matches ``self._template``. ``segment`` holds input from
        frame ``first``."""
        hop, search, dec = self.hop, self.search, DECIMATE
        lo = max(0, nominal - search)
        hi = nominal + search
        if hi <= lo:
            return lo
        mono = segment.sum(axis=0)
        ref = template.sum(axis=0)
        # Coarse: decimated mono, normalised cross-correlation per candidate;
        # candidate k starts at frame ``first + k * dec``.
        n_ref = (hop // dec) * dec
        refd = ref[:n_ref].reshape(-1, dec).mean(axis=1)
        cut = (len(mono) // dec) * dec
        cd = mono[:cut].reshape(-1, dec).mean(axis=1)
        if len(cd) < len(refd) + 1:
            return nominal
        dots = np.correlate(cd, refd, mode="valid")
        sq = np.concatenate([[0.0], np.cumsum(cd.astype(np.float64) ** 2)])
        energy = sq[len(refd):len(refd) + len(dots)] - sq[:len(dots)]
        score = dots / np.sqrt(energy + 1e-9)
        k_lo = math.ceil((lo - first) / dec)
        k_hi = min(len(score) - 1, (hi - first) // dec)
        if k_hi < k_lo:
            return nominal
        best = first + (k_lo + int(np.argmax(score[k_lo:k_hi + 1]))) * dec
        # Fine: every frame within +-dec of the coarse winner.
        flo, fhi = max(lo, best - dec), min(hi, best + dec)
        scores = []
        for s in range(flo, fhi + 1):
            i = s - first
            piece = mono[i:i + hop]
            if len(piece) < hop:
                break
            scores.append((float(piece @ ref) / math.sqrt(float(piece @ piece) + 1e-9),
                           s))
        return max(scores)[1] if scores else best

    # -- output ------------------------------------------------------------------

    def next_hop(self) -> np.ndarray | None:
        """The next ``(hop, 2)`` float32 output block, or None after the end."""
        if self._ended:
            return None
        if self._draining:  # the last grain's falling half, then the end
            self._ended = True
            return np.ascontiguousarray(self._tail.T)
        hop = self.hop
        nominal = round(self._pos)
        if self._template is None:
            # The first grain starts exactly at the start: no search, no
            # fade-in; its rising half is played as it is.
            start = nominal
            data = self._input(start, start + 2 * hop)
            grain = data
            out = grain[:, :hop].copy()
        else:
            lo = max(0, nominal - self.search)
            segment = self._input(lo, nominal + self.search + 2 * hop)
            start = self._best_start(nominal, segment, lo, self._template)
            grain = segment[:, start - lo:start - lo + 2 * hop]
            if grain.shape[1] < 2 * hop:  # cannot happen: _get pads with silence
                grain = np.pad(grain, ((0, 0), (0, 2 * hop - grain.shape[1])))
            out = self._tail + grain[:, :hop] * self._window[:hop]
        self._template = np.array(grain[:, hop:2 * hop])
        self._tail = self._template * self._window[hop:]
        self._pos += hop * self.speed
        if self._pos >= self.length:
            self._draining = True  # the tail is the last block
        return np.ascontiguousarray(out.T)
