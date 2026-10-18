"""Alignment maths for "align by sound".

Pure functions over lag measurements.  Each measurement is a tuple of
``(time_seconds, lag_seconds, peak_ratio)`` where ``peak_ratio`` is the ratio
of the best correlation peak to the second-best peak.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

# 1 ms per 10 minutes, expressed as seconds of lag per second.
_DRIFT_THRESHOLD = 0.001 / 600

#: A window counts as clear when its best peak is this many times the second best.
_MIN_RATIO = 1.5


def clear_windows(
    measurements: Sequence[tuple[float, float, float]],
    *,
    min_ratio: float | None = None,
) -> list[tuple[float, float, float]]:
    """Return measurements whose ``peak_ratio`` is at least ``min_ratio``."""
    threshold = _MIN_RATIO if min_ratio is None else min_ratio
    return [m for m in measurements if m[2] >= threshold]


def fit_drift(
    measurements: Sequence[tuple[float, float, float]],
) -> tuple[float, float] | None:
    """Fit a least-squares line to the clear measurements.

    Returns ``(offset_seconds, slope)`` where ``lag = offset + slope * time``,
    or ``None`` when fewer than two clear measurements are available.
    """
    clear = clear_windows(measurements)
    if len(clear) < 2:
        return None
    times = np.array([m[0] for m in clear], dtype=np.float64)
    lags = np.array([m[1] for m in clear], dtype=np.float64)
    slope, offset = np.polyfit(times, lags, 1)
    return float(offset), float(slope)


def has_drift(slope: float) -> bool:
    """Return True when the absolute slope exceeds 1 ms per 10 minutes."""
    return abs(slope) > _DRIFT_THRESHOLD


def resample_ratio(slope: float) -> float:
    """Return the resampling ratio implied by the drift slope."""
    return 1.0 + slope


def jumps(
    measurements: Sequence[tuple[float, float, float]],
    offset: float,
    slope: float,
    *,
    tolerance: float = 0.020,
) -> tuple[int, ...]:
    """Return original indices of clear measurements that jump off the fit.

    A measurement is flagged when the absolute difference between its lag and
    the fitted lag at its time is greater than ``tolerance``.
    """
    clear = clear_windows(measurements)
    result = []
    for original_index, (time, lag, _ratio) in zip(
        (i for i, m in enumerate(measurements) if m[2] >= _MIN_RATIO),
        clear,
        strict=True,
    ):
        fitted = offset + slope * time
        if abs(lag - fitted) > tolerance:
            result.append(original_index)
    return tuple(result)


def split_point(
    levels: Sequence[tuple[float, float]],
    start: float,
    end: float,
) -> float | None:
    """Return the time of the lowest level in ``[start, end]``.

    Ties are resolved by returning the earliest time.  Returns ``None`` when
    no level falls inside the range.
    """
    best_time: float | None = None
    best_level: float | None = None
    for time, level in levels:
        if not start <= time <= end:
            continue
        if best_level is None or level < best_level:
            best_time = time
            best_level = level
    return best_time
