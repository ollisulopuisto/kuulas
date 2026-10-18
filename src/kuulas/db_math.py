"""Decibel arithmetic helpers.

``db_to_gain`` and ``gain_to_db`` convert between decibels and linear gain,
``sum_db`` and ``mean_db`` sum and average power in the dB domain, and
``clamp_db`` clamps a level to an interval. Errors are plain ``ValueError``;
there is no user-facing text. Inputs are never mutated.
"""

from __future__ import annotations

import math


def db_to_gain(db: float) -> float:
    """Return the linear gain for ``db`` decibels: ``10 ** (db / 20)``.

    ``nan`` raises ``ValueError``; ``-inf`` (silence) yields a gain of 0.0.
    """
    if math.isnan(db):
        msg = f"db must be a number, got {db!r}"
        raise ValueError(msg)
    return 10.0 ** (db / 20.0)


def gain_to_db(gain: float, floor_db: float = -120.0) -> float:
    """Return ``20 * log10(gain)``, or ``floor_db`` for ``gain <= 0``.

    ``nan`` gain raises ``ValueError``.
    """
    if math.isnan(gain):
        msg = f"gain must be a number, got {gain!r}"
        raise ValueError(msg)
    if gain <= 0.0:
        return floor_db
    return 20.0 * math.log10(gain)


def sum_db(levels: list[float]) -> float:
    """Return the power sum of ``levels``: ``10 * log10(sum(10 ** (l / 10)))``.

    An empty list gives ``float("-inf")``. ``nan`` raises ``ValueError``;
    ``-inf`` levels count as silence.
    """
    if any(math.isnan(level) for level in levels):
        msg = f"levels must not contain nan, got {levels!r}"
        raise ValueError(msg)
    total = sum(10.0 ** (level / 10.0) for level in levels)
    if total <= 0.0:
        return float("-inf")
    return 10.0 * math.log10(total)


def mean_db(levels: list[float]) -> float:
    """Return the power mean of ``levels``: the sum minus ``10 * log10(n)``.

    An empty list gives ``float("-inf")``. ``nan`` raises ``ValueError``;
    ``-inf`` levels count as silence.
    """
    count = len(levels)
    if count == 0:
        return float("-inf")
    if any(math.isnan(level) for level in levels):
        msg = f"levels must not contain nan, got {levels!r}"
        raise ValueError(msg)
    return sum_db(levels) - 10.0 * math.log10(count)


def clamp_db(db: float, lo: float, hi: float) -> float:
    """Return ``db`` clamped to the interval ``[lo, hi]``.

    ``lo > hi`` raises ``ValueError``, as does a ``nan`` input.
    """
    if lo > hi:
        msg = f"lo ({lo}) must not be greater than hi ({hi})"
        raise ValueError(msg)
    if math.isnan(db):
        msg = f"db must be a number, got {db!r}"
        raise ValueError(msg)
    return min(max(db, lo), hi)
