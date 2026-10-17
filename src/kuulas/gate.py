"""A track's gate: merged closed ranges, Auto-Silence's new form (WP44).

Auto-Silence used to split a clip at every closed stretch, which left
thousands of pieces on a long session (the WP44 problem). The measurement
stays that fine; the result is one merged gate per track, stored as a tuple
of ``(start, end)`` frame pairs, sorted, non-overlapping and not touching.

This module is the pure arithmetic only — no model, session or mixer import.
The wiring (``Track.gate``, the mixer's 30 ms ramp, the audibility rules)
and the second-to-frame constants (``MIN_OPEN_S`` / ``MIN_CLOSED_S`` next to
``OPEN_BEFORE_S`` in ``analysis``) come later. Thresholds arrive as frames.

"Closed" is the gate's own word for muted: a closed range is where the mic
is shut; an open stretch is the gap between two closed ranges.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable

import numpy as np

#: One closed stretch: [start, end) in frames.
Range = tuple[int, int]
#: A whole gate: sorted, non-overlapping, not touching, no empty ranges.
Gate = tuple[Range, ...]


def normalise(ranges: Iterable[Range]) -> Gate:
    """Any bunch of ranges as a proper gate: sorted, empty and reversed
    ranges dropped, ranges that overlap or touch unioned into one.

    Touching ranges merge because a half-open gate has no use for two
    ranges that meet at a frame: the mic would close and open at the same
    frame, and one range says the same thing.
    """
    kept = sorted((int(start), int(end)) for start, end in ranges if end > start)
    merged: list[Range] = []
    for start, end in kept:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def merge_ranges(ranges: Iterable[Range], min_open: int, min_closed: int) -> Gate:
    """Normalise, then close every open stretch (the gap between two
    ranges) shorter than ``min_open`` frames, then drop every range shorter
    than ``min_closed`` frames, in that order (WP44 rule 1).

    The order matters: closing first can save short pieces — two short
    ranges with a still shorter gap bridge into one long range and clear
    ``min_closed``; dropping first would lose both. A drop can then leave a
    gap shorter than ``min_open`` between the survivors; it stays open,
    because the drop runs last and the two steps are not iterated.
    """
    bridged: list[Range] = []
    for start, end in normalise(ranges):
        if bridged and start - bridged[-1][1] < min_open:
            # The gap is too short to be worth reopening the mic for.
            bridged[-1] = (bridged[-1][0], end)
        else:
            bridged.append((start, end))
    return tuple((start, end) for start, end in bridged if end - start >= min_closed)


def ranges_from_mask(mask: np.ndarray, hop: int) -> Gate:
    """The closed frame ranges of a boolean mask: ``True`` means closed, and
    each mask step covers ``hop`` frames.

    Vectorised — one ``np.diff`` and one ``np.flatnonzero`` find the run
    edges, no Python loop over the samples — because a one-hour mask at
    ``grid.HOP`` is 360,000 steps. The padding turns the first and last
    edge into ordinary run edges, so a run at either end of the mask is
    found like any other.
    """
    m = np.asarray(mask, dtype=bool)
    if m.size == 0:
        return ()
    # int8, because numpy refuses to subtract booleans.
    edges = np.flatnonzero(np.diff(np.concatenate(([0], m.astype(np.int8), [0]))))
    starts = edges[0::2] * hop
    ends = edges[1::2] * hop
    return tuple(zip(starts.tolist(), ends.tolist(), strict=True))


def add_range(gate: Gate, start: int, end: int) -> Gate:
    """One more closed range, merged into the gate.

    An empty or reversed span adds nothing: normalise drops it, the gate
    comes back unchanged.
    """
    return normalise((*gate, (start, end)))


def remove_range(gate: Gate, start: int, end: int) -> Gate:
    """The gate without the span ``[start, end)``: every range that overlaps
    it loses the overlap, and a range spanning it falls into two.

    An empty or reversed span removes nothing. The result needs no second
    normalisation: each part lies inside its source range, the source
    ranges are disjoint and do not touch, and the two parts of one range
    are separated by the span itself.
    """
    if start >= end:
        return normalise(gate)
    out: list[Range] = []
    for a, b in normalise(gate):
        if a < start:
            out.append((a, min(b, start)))
        if b > end:
            out.append((max(a, end), b))
    return tuple(out)


def ripple(gate: Gate, cut_start: int, cut_end: int) -> Gate:
    """What a ripple delete of ``[cut_start, cut_end)`` does to the gate:
    ranges after the cut shift left by its length, a range that overlaps
    the cut loses the overlap, ranges inside it vanish, and ranges that now
    touch merge.

    A range covering the whole cut is the interesting one: the stretch
    before the cut stays, the stretch after it shifts left onto exactly
    that frame, and the merge closes them into one range.
    """
    if cut_start >= cut_end:
        return normalise(gate)
    length = cut_end - cut_start
    moved: list[Range] = []
    for a, b in normalise(gate):
        # The stretch before the cut keeps its place, the stretch after it
        # shifts left by the cut's length, and the stretch inside it — the
        # overlap — is deleted with the cut.
        if a < cut_start:
            moved.append((a, min(b, cut_start)))
        if b > cut_end:
            moved.append((max(a, cut_end) - length, b - length))
    return normalise(moved)


def closed_at(gate: Gate, frame: int) -> bool:
    """Is the mic shut at ``frame``? Ranges are half-open: the first frame
    of a range is closed, its end frame is open again."""
    i = bisect_right(gate, (frame, float("inf"))) - 1
    return i >= 0 and gate[i][0] <= frame < gate[i][1]


def split_by_gate(gate: Gate, start: int, end: int) -> list[tuple[int, int, bool]]:
    """``[start, end)`` cut at the gate's edges, as ``(from, to, open)``
    pieces in order. The audibility rules (usage, collateral) read a clip
    through this, so a gated stretch is inaudible exactly as a muted clip is.
    """
    if end <= start:
        return []
    out: list[tuple[int, int, bool]] = []
    at = start
    i = max(0, bisect_left(gate, (start,)) - 1)
    while i < len(gate) and gate[i][0] < end:
        a, b = gate[i]
        i += 1
        if b <= at:
            continue
        if a > at:
            out.append((at, a, True))
        lo, hi = max(a, at), min(b, end)
        out.append((lo, hi, False))
        at = hi
    if at < end:
        out.append((at, end, True))
    return out


def full_hops(gate: Gate, hops: int, hop: int) -> np.ndarray:
    """Boolean mask over ``hops`` steps of ``hop`` frames: True where the
    whole step lies inside one closed range. A step the gate only touches
    is still partly audible, so it stays False."""
    mask = np.zeros(hops, dtype=bool)
    for a, b in gate:
        lo, hi = -(-a // hop), b // hop  # first whole step in, last whole step out
        if hi > lo:
            mask[lo:min(hi, hops)] = True
    return mask
