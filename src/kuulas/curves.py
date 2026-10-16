"""Breakpoint curves: ``[(frame, dB), ...]``, linear in dB between points.

Before the first point the curve holds the first value, after the last it
holds the last; an empty curve is 0 dB. The mixer and the ripple edit read
the same function, so a cut cannot change what the automation sounds like.
"""

from __future__ import annotations

import numpy as np


def value_at(points, frame: int) -> float:
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return float(np.interp(frame, xs, ys))


def db_curve(points, first: int, count: int) -> np.ndarray | None:
    """dB per frame over ``[first, first + count)``, or None for an empty curve."""
    if not points:
        return None
    xs = np.fromiter((p[0] for p in points), dtype=np.float64)
    ys = np.fromiter((p[1] for p in points), dtype=np.float64)
    frames = np.arange(first, first + count, dtype=np.float64)
    return np.interp(frames, xs, ys)


def gain(db) -> np.ndarray | float:
    return np.power(10.0, np.asarray(db) / 20.0)
