"""Merging and subtracting frame ranges.

Ranges are ``(start, end)`` pairs of whole frames with ``end > start``.
``merge_ranges`` sorts and joins overlapping or nearby ranges,
``subtract_ranges`` removes holes, and ``total_length`` sums the merged span.
Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations


def _check_range(range_: tuple[int, int]) -> tuple[int, int]:
    start, end = range_
    if end <= start:
        msg = f"range {range_} must have end > start"
        raise ValueError(msg)
    return start, end


def merge_ranges(
    ranges: list[tuple[int, int]], gap: int = 0
) -> list[tuple[int, int]]:
    """Return a new sorted list with overlapping or nearby ranges joined.

    Two ranges join when they overlap or touch, or when the distance between
    them (next start minus current end) is at most ``gap``. Touching ranges
    always join. ``gap < 0`` raises ``ValueError``. The input is not mutated.
    """
    if gap < 0:
        msg = f"gap must not be negative, got {gap}"
        raise ValueError(msg)

    merged: list[list[int]] = []
    for start, end in sorted(
        (_check_range(range_) for range_ in ranges), key=lambda range_: range_[0]
    ):
        if merged and start <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def subtract_ranges(
    ranges: list[tuple[int, int]], holes: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Return the parts of ``ranges`` not covered by any of ``holes``.

    Both inputs are merged first. The result is sorted and has no empty
    pieces. Neither input is mutated.
    """
    kept = merge_ranges(ranges)
    merged_holes = merge_ranges(holes)

    result: list[tuple[int, int]] = []
    hole_index = 0
    for start, end in kept:
        while (
            hole_index < len(merged_holes)
            and merged_holes[hole_index][1] <= start
        ):
            hole_index += 1
        cursor = start
        while (
            hole_index < len(merged_holes)
            and merged_holes[hole_index][0] < end
        ):
            hole_start, hole_end = merged_holes[hole_index]
            if hole_start > cursor:
                result.append((cursor, min(hole_start, end)))
            cursor = max(cursor, hole_end)
            if cursor >= end:
                break
            hole_index += 1
        if cursor < end:
            result.append((cursor, end))
    return result


def total_length(ranges: list[tuple[int, int]]) -> int:
    """Return the summed length of the ranges after merging."""
    return sum(end - start for start, end in merge_ranges(ranges))
