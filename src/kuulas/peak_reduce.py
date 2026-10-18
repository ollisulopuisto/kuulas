"""Peak envelope downsampling.

``reduce_peaks`` collapses each group of ``factor`` consecutive
``(min, max)`` peak pairs to ``(min of mins, max of maxes)``.
``levels_to_bars`` splits the peaks into nearly equal groups and returns
one ``(min, max)`` bar per group. Errors are plain ``ValueError``;
there is no user-facing text. Inputs are never mutated.
"""

from __future__ import annotations


def reduce_peaks(
    peaks: list[tuple[float, float]], factor: int
) -> list[tuple[float, float]]:
    """Return one ``(min, max)`` pair per group of ``factor`` pairs.

    Each group becomes ``(min of the mins, max of the maxes)``; a short
    last group is reduced too. ``factor < 1`` raises ``ValueError``,
    ``factor == 1`` returns an equal copy, and an empty list gives
    ``[]``. The input is not mutated.
    """
    if factor < 1:
        msg = f"factor must be at least 1, got {factor}"
        raise ValueError(msg)
    result: list[tuple[float, float]] = []
    for index in range(0, len(peaks), factor):
        group = peaks[index : index + factor]
        result.append(
            (
                min(minimum for minimum, _ in group),
                max(maximum for _, maximum in group),
            )
        )
    return result


def levels_to_bars(
    peaks: list[tuple[float, float]], bars: int
) -> list[tuple[float, float]]:
    """Return one ``(min, max)`` bar per group.

    The peaks are split into ``bars`` nearly equal groups: sizes differ
    by at most one and earlier groups are larger. Fewer peaks than bars
    returns one bar per peak. ``bars < 1`` raises ``ValueError``. The
    input is not mutated.
    """
    if bars < 1:
        msg = f"bars must be at least 1, got {bars}"
        raise ValueError(msg)
    count = len(peaks)
    if count <= bars:
        return list(peaks)
    base, extra = divmod(count, bars)
    result: list[tuple[float, float]] = []
    start = 0
    for index in range(bars):
        size = base + (1 if index < extra else 0)
        group = peaks[start : start + size]
        start += size
        result.append(
            (
                min(minimum for minimum, _ in group),
                max(maximum for _, maximum in group),
            )
        )
    return result
