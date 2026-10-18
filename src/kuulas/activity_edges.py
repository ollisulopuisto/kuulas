"""Activity edges of a track from a loudness series.

``activity_edges(levels_db, hop, threshold_db, min_active, min_gap)`` returns
the frame spans of consecutive levels at or above ``threshold_db`` whose span
is at least ``min_active`` frames long; two stretches separated by a quiet gap
shorter than ``min_gap`` frames are merged into one. ``edge_frames(stretches)``
returns the sorted, de-duplicated list of all stretch start and end frames.
Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations


def activity_edges(
    levels_db: list[float],
    hop: int,
    threshold_db: float,
    min_active: int,
    min_gap: int,
) -> list[dict[str, int]]:
    """Return ``{"start", "end"}`` stretches of active levels.

    A stretch is a maximal run of consecutive levels at or above
    ``threshold_db`` whose length in frames (``run_count * hop``) is at least
    ``min_active``; its ``start`` is the first level's index times ``hop`` and
    its ``end`` is one past the last level times ``hop``. Two stretches
    separated by a quiet gap shorter than ``min_gap`` frames are merged into
    one. The input is not mutated.
    """
    if hop <= 0:
        msg = f"hop must be positive, got {hop}"
        raise ValueError(msg)
    if min_active < 0:
        msg = f"min_active must not be negative, got {min_active}"
        raise ValueError(msg)
    if min_gap < 0:
        msg = f"min_gap must not be negative, got {min_gap}"
        raise ValueError(msg)

    stretches: list[tuple[int, int]] = []
    run_start: int | None = None
    for index, level in enumerate(levels_db):
        if level >= threshold_db:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            if (index - run_start) * hop >= min_active:
                stretches.append((run_start * hop, index * hop))
            run_start = None
    if run_start is not None:
        count = len(levels_db) - run_start
        if count * hop >= min_active:
            stretches.append((run_start * hop, len(levels_db) * hop))

    merged: list[tuple[int, int]] = []
    for start, end in stretches:
        if merged and start - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    return [{"start": start, "end": end} for start, end in merged]


def edge_frames(stretches: list[dict[str, int]]) -> list[int]:
    """Return the sorted, de-duplicated start and end frames of ``stretches``."""
    frames: list[int] = []
    for stretch in stretches:
        frames.append(stretch["start"])
        frames.append(stretch["end"])
    return sorted(set(frames))
