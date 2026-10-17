"""What changed between two project states, on the recording clock (WP31).

The first half of the changes view: which stretches of a recording are
audible in one state and not the other. Positions are flicks on the
recording's own clock (``usage``), so a change is found however the clips
are arranged on the timeline. Ranges whose gain, mute, ducking, FX or take
differ are a later part of WP31; here audibility alone decides.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Project
from .usage import extract


@dataclass(frozen=True)
class Change:
    """One stretch of a recording audible in only one of the two states."""

    kind: str  # "removed": audible in a, not in b; "added": audible in b, not in a
    media_sha256: str
    from_flicks: int
    to_flicks: int


def _audible(project: Project) -> dict[str, list[tuple[int, int]]]:
    """Each recording's audible ranges on its own clock, merged into a union."""
    # Report uses merge gaps of up to 2 s (``usage``'s default); a change
    # view must see every cut, so only ranges that touch are merged, in
    # ``_union`` below.
    ranges: dict[str, list[tuple[int, int]]] = {}
    for use in extract(project, merge_gap=0):
        if use.audible:
            ranges.setdefault(use.media_sha256, []).append(
                (use.from_flicks, use.to_flicks))
    return {digest: _union(items) for digest, items in ranges.items()}


def _union(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The sorted union: ranges that overlap or touch become one."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _uncovered(ranges: list[tuple[int, int]],
               cover: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The parts of the union ``ranges`` that the union ``cover`` leaves out.

    Both arguments come from ``_union``, so both are sorted and disjoint,
    which is what lets the walk stop at the first cover range past the end.
    """
    out: list[tuple[int, int]] = []
    for start, end in ranges:
        cursor = start
        for cover_start, cover_end in cover:
            if cover_start >= end:
                break
            if cover_end <= cursor:
                continue
            if cover_start > cursor:
                out.append((cursor, cover_start))
            cursor = cover_end
            if cursor >= end:
                break
        if cursor < end:
            out.append((cursor, end))
    return out


def diff(a: Project, b: Project) -> tuple[Change, ...]:
    """The recording ranges audible in ``a`` and not in ``b`` (``"removed"``),
    and audible in ``b`` and not in ``a`` (``"added"``).

    Each state's audible uses (``usage.extract``) are merged into one union
    per recording, and the unions are subtracted from each other, so the
    result follows the recorded content, not the clips' arrangement. The
    changes are sorted by recording and start.
    """
    a_ranges = _audible(a)
    b_ranges = _audible(b)
    changes: list[Change] = []
    for digest in sorted(a_ranges.keys() | b_ranges.keys()):
        for start, end in _uncovered(a_ranges.get(digest, []),
                                     b_ranges.get(digest, [])):
            changes.append(Change("removed", digest, start, end))
        for start, end in _uncovered(b_ranges.get(digest, []),
                                     a_ranges.get(digest, [])):
            changes.append(Change("added", digest, start, end))
    return tuple(sorted(changes, key=lambda c: (c.media_sha256, c.from_flicks,
                                                c.to_flicks, c.kind)))
