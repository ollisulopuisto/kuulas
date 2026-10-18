"""Waveform clipping after gain.

Where the level after gain passes full scale: runs of consecutive peak pairs,
and the largest level above full scale in dB. Pure Python, stdlib only: no
imports from kuulas. Errors are plain ValueError; there is no user-facing text.
"""

from __future__ import annotations

import math


def overs(peaks: list[tuple[float, float]], gain_db: float,
          limit_db: float = -0.1) -> list[tuple[int, int]]:
    """Return ``(first_index, last_index_inclusive)`` over-limit runs.

    A peak pair is over the limit when its absolute peak after gain,
    ``max(abs(min), abs(max)) * 10 ** (gain_db / 20)``, is above
    ``10 ** (limit_db / 20)``. Consecutive over-limit pairs form one run.

    Raises ``ValueError`` for ``limit_db > 0`` or a non-finite ``gain_db``.
    The input is not mutated.
    """
    if not math.isfinite(gain_db):
        msg = f"gain_db ({gain_db}) must be finite"
        raise ValueError(msg)
    if limit_db > 0:
        msg = f"limit_db ({limit_db}) must be <= 0"
        raise ValueError(msg)

    gain = 10 ** (gain_db / 20)
    limit = 10 ** (limit_db / 20)

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, (mn, mx) in enumerate(peaks):
        level = max(abs(mn), abs(mx)) * gain
        if level > limit:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index - 1))
            start = None
    if start is not None:
        runs.append((start, len(peaks) - 1))
    return runs


def max_over_db(peaks: list[tuple[float, float]], gain_db: float) -> float:
    """Return the largest level above full scale in dB, or 0.0.

    The level of a peak pair after gain is
    ``max(abs(min), abs(max)) * 10 ** (gain_db / 20)``; the result is
    ``20 * log10`` of the largest level, or 0.0 when nothing is over full
    scale or the list is empty.

    Raises ``ValueError`` for a non-finite ``gain_db``. The input is not
    mutated.
    """
    if not math.isfinite(gain_db):
        msg = f"gain_db ({gain_db}) must be finite"
        raise ValueError(msg)

    gain = 10 ** (gain_db / 20)
    max_level = 0.0
    for mn, mx in peaks:
        level = max(abs(mn), abs(mx)) * gain
        max_level = max(max_level, level)
    if max_level <= 0.0:
        return 0.0
    db = 20 * math.log10(max_level)
    return db if db > 0.0 else 0.0
