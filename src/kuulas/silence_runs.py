"""Silence runs from a loudness series.

``silence_runs(levels_db, hop, threshold_db, min_len)`` returns the frame
spans of consecutive levels below ``threshold_db`` whose span is at least
``min_len`` frames long. Levels equal to the threshold are not silent.
Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations


def silence_runs(
    levels_db: list[float], hop: int, threshold_db: float, min_len: int
) -> list[tuple[int, int]]:
    """Return ``(start_frame, end_frame)`` for each silent run.

    A run is a maximal sequence of consecutive levels below ``threshold_db``;
    its length in frames is ``run_count * hop`` and it is reported only when
    that length is at least ``min_len``. ``start`` is the first level's index
    times ``hop``, ``end`` is one past the last level times ``hop``. The input
    is not mutated.
    """
    if hop <= 0:
        msg = f"hop must be positive, got {hop}"
        raise ValueError(msg)
    if min_len < 0:
        msg = f"min_len must not be negative, got {min_len}"
        raise ValueError(msg)

    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for index, level in enumerate(levels_db):
        if level < threshold_db:
            if run_start is None:
                run_start = index
        elif run_start is not None:
            if (index - run_start) * hop >= min_len:
                runs.append((run_start * hop, index * hop))
            run_start = None
    if run_start is not None:
        count = len(levels_db) - run_start
        if count * hop >= min_len:
            runs.append((run_start * hop, len(levels_db) * hop))
    return runs
