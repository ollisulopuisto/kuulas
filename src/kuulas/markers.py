"""Markers, regions and chapters: how they move with ripple edits (WP19h).

Pure functions on tuples of ``Marker``. A marker is a named point, a region a
named range, a chapter a point that goes in the chapter list. All are timeline
frames and part of the edit state, so they move with the audio the way the
automation and the gate do.
"""

from __future__ import annotations

from dataclasses import replace

from .model import Marker

KINDS = ("marker", "region", "chapter")


def ordered(markers) -> tuple[Marker, ...]:
    return tuple(sorted(markers, key=lambda m: (m.start, m.id)))


def _after_cut(frame: int, start: int, end: int) -> int:
    """Where ``frame`` lands when ``[start, end)`` is removed: a frame inside
    the cut goes to the cut start, one after it moves left by the cut."""
    if frame <= start:
        return frame
    if frame < end:
        return start
    return frame - (end - start)


def ripple(markers, cut_start: int, cut_end: int) -> tuple[Marker, ...]:
    """What a ripple delete of ``[cut_start, cut_end)`` does to ``markers``.

    A point inside the cut moves to the cut start. A region loses the overlap
    and goes if nothing is left of it (as ``gate.ripple`` does for ranges).
    """
    if cut_end <= cut_start:
        return ordered(markers)
    out = []
    for m in markers:
        start = _after_cut(m.start, cut_start, cut_end)
        if m.end is None:
            out.append(replace(m, start=start))
            continue
        end = _after_cut(m.end, cut_start, cut_end)
        if end > start:
            out.append(replace(m, start=start, end=end))
    return ordered(out)


def open_gap(markers, at: int, length: int) -> tuple[Marker, ...]:
    """The inverse: ``length`` empty frames opened at ``at``. What lies
    after ``at`` moves right; a region that straddles it is stretched; a
    marker exactly at ``at`` stays before the new material."""
    if length <= 0:
        return ordered(markers)
    out = []
    for m in markers:
        end = None if m.end is None else (m.end + length if m.end > at else m.end)
        start = m.start + length if m.start > at else m.start
        out.append(replace(m, start=start, end=end))
    return ordered(out)


def chapters(markers) -> list[tuple[int, str]]:
    """``(frame, title)`` for every chapter, as ``chapters.format_chapters`` takes."""
    return [(m.start, m.name) for m in ordered(markers) if m.kind == "chapter"]


def regions(markers) -> list[Marker]:
    return [m for m in ordered(markers) if m.kind == "region"]
