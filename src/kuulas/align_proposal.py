"""Conservative whole-clip proposals, never edits, from sound measurements.

A robust straight-line consensus can propose a fixed offset and clock ratio.
Discontinuous or competing matches deliberately produce no proposal here: a
separate boundary-refinement stage must account for missing audio first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np


@dataclass(frozen=True)
class Proposal:
    """Lag = offset + slope * source time, with original measurement indices."""

    offset: float
    slope: float
    support: tuple[int, ...]
    excluded: tuple[int, ...]


def propose(measurements: list[tuple[float, float, float]], *,
            tolerance: float = .004, max_drift: float = .002,
            min_separation: float = 10.) -> Proposal | None:
    """Require independent support for >=80% of clear windows and time span.

    Defaults allow 4 ms residual and 2000 ppm clock mismatch. These are safety
    limits, not a claim that a larger clock mismatch is impossible. The caller
    must show the resulting proposal for confirmation before moving any audio.
    Near-duplicate/overlapping windows never increase the independent count.
    Invalid measurements and unbounded input fail closed.
    """
    if (len(measurements) > 256 or not math.isfinite(tolerance) or tolerance <= 0
            or not math.isfinite(max_drift) or max_drift <= 0
            or not math.isfinite(min_separation) or min_separation <= 0):
        return None
    if any(not all(math.isfinite(v) for v in point) or point[0] < 0
           for point in measurements):
        return None
    clear = sorted((t, lag, index) for index, (t, lag, ratio) in enumerate(measurements)
                   if ratio >= 1.5)
    independent = []
    for point in clear:
        if not independent or point[0] - independent[-1][0] >= min_separation:
            independent.append(point)
    if len(independent) < 3:
        return None
    times = np.array([point[0] for point in independent])
    lags = np.array([point[1] for point in independent])
    span = times[-1] - times[0]
    required = max(3, math.ceil(.8 * len(independent)))
    best = None
    # Exhaustive pair consensus is bounded (the measurement pass emits ~13
    # windows). Quality ratios do not weight the fit: an isolated loud match
    # must not outweigh several independent agreements.
    for a, b in combinations(range(len(times)), 2):
        slope = (lags[b] - lags[a]) / (times[b] - times[a])
        if abs(slope) > max_drift:
            continue
        offset = lags[a] - slope * times[a]
        mask = np.abs(lags - (offset + slope * times)) <= tolerance
        if int(mask.sum()) < required or np.ptp(times[mask]) < .8 * span:
            continue
        slope, offset = np.polyfit(times[mask], lags[mask], 1)
        residual = np.abs(lags - (offset + slope * times))
        # Refitting must not pull an accepted point outside tolerance.
        if abs(slope) > max_drift or np.any(residual[mask] > tolerance):
            continue
        score = (int(mask.sum()), -float(np.mean(residual[mask])))
        if best is None or score > best[0]:
            best = (score, float(offset), float(slope), mask)
    if best is None:
        return None
    _, offset, slope, mask = best
    support = tuple(sorted(point[2] for point, yes
                           in zip(independent, mask, strict=True) if yes))
    return Proposal(offset, slope, support,
                    tuple(i for i in range(len(measurements)) if i not in support))
