"""Narration placeholders: how they move with ripple edits (WP43).

Pure functions on tuples of ``Placeholder``. A placeholder is a range of one
track, so, unlike a marker (which sits on the whole timeline), it moves with
the tracks a ripple touches: ``scope`` is the set of track ids that were cut
or opened.
"""

from __future__ import annotations

from dataclasses import replace

from .model import Placeholder


def ordered(items) -> tuple[Placeholder, ...]:
    return tuple(sorted(items, key=lambda h: (h.start, h.track, h.id)))


def _after_cut(frame: int, start: int, end: int) -> int:
    if frame <= start:
        return frame
    if frame < end:
        return start
    return frame - (end - start)


def ripple(items, scope, cut_start: int, cut_end: int) -> tuple[Placeholder, ...]:
    """What a ripple delete of ``[cut_start, cut_end)`` on the tracks in
    ``scope`` does: later ones move left, one that overlaps the cut loses the
    overlap (its length is then no longer the text's estimate) and one that is
    all inside the cut goes."""
    if cut_end <= cut_start:
        return ordered(items)
    out = []
    for h in items:
        if h.track not in scope:
            out.append(h)
            continue
        start = _after_cut(h.start, cut_start, cut_end)
        end = _after_cut(h.end, cut_start, cut_end)
        if end <= start:
            continue
        length = end - start
        out.append(replace(h, start=start, length=length,
                           estimated=h.estimated and length == h.length))
    return ordered(out)


def open_gap(items, scope, at: int, length: int) -> tuple[Placeholder, ...]:
    """The inverse: ``length`` empty frames opened at ``at`` on the tracks in
    ``scope``. A placeholder that starts at or after ``at`` moves right (as a
    clip does); one that straddles it is stretched, and keeps its estimate
    flag only in name: the user stretched nothing, so the text still rules."""
    if length <= 0:
        return ordered(items)
    out = []
    for h in items:
        if h.track not in scope:
            out.append(h)
        elif h.start >= at:
            out.append(replace(h, start=h.start + length))
        elif h.end > at:
            out.append(replace(h, length=h.length + length, estimated=False))
        else:
            out.append(h)
    return ordered(out)


def unrecorded(items, start: int, end: int) -> tuple[Placeholder, ...]:
    """The placeholders that overlap ``[start, end)``."""
    return tuple(h for h in ordered(items) if h.start < end and h.end > start)
