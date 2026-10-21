"""A NumPy-only sidechain law used by the speech-triggered music duck.

The trigger is expected to be a mono sum of speech after track processing. The
caller matches its gated speech loudness to ``reference_lufs`` before passing
it here; this makes the default -30 dB threshold comparable to the automixer's
processed speech without baking any gain into the music automation.
"""

from __future__ import annotations

import numpy as np


def gain_curve_db(
    trigger,
    rate,
    *,
    threshold_db=-30.0,
    ratio=8.0,
    window_s=0.1,
    attack_s=0.05,
    release_s=0.3,
    floor_db=-24.0,
):
    """Return the smoothed sidechain gain reduction in dB for a mono signal."""
    signal = np.asarray(trigger, dtype=np.float64).reshape(-1)
    rate = float(rate)
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError
    if not np.isfinite(ratio) or ratio < 1:
        raise ValueError
    if window_s <= 0 or attack_s <= 0 or release_s <= 0:
        raise ValueError
    if floor_db > 0:
        raise ValueError
    if signal.size == 0:
        return np.empty(0, dtype=np.float64)

    width = max(1, round(float(window_s) * rate))
    left = (width - 1) // 2
    padded = np.pad(signal * signal, (left, width - 1 - left))
    prefix = np.empty(padded.size + 1, dtype=np.float64)
    prefix[0] = 0.0
    np.cumsum(padded, out=prefix[1:])
    rms = np.sqrt(np.maximum(0.0, (prefix[width:] - prefix[:-width]) / width))
    level_db = 20.0 * np.log10(np.maximum(rms, 1e-12))
    over = np.maximum(0.0, level_db - threshold_db)
    target = np.minimum(0.0, -(over * (1 - 1 / ratio)))
    target = np.maximum(target, floor_db)

    attack = np.exp(-1.0 / (rate * attack_s))
    release = np.exp(-1.0 / (rate * release_s))
    result = np.empty(signal.size, dtype=np.float64)
    current = 0.0
    for index, desired in enumerate(target):
        coefficient = attack if desired < current else release
        current = desired + coefficient * (current - desired)
        result[index] = min(0.0, max(floor_db, current))
    return result


def _segment_error(values: np.ndarray, first: int, last: int) -> tuple[float, int]:
    span = last - first
    if span <= 1:
        return 0.0, first
    indices = np.arange(first + 1, last)
    line = values[first] + (values[last] - values[first]) * ((indices - first) / span)
    errors = np.abs(values[first + 1:last] - line)
    offset = int(np.argmax(errors))
    return float(errors[offset]), first + 1 + offset


def curve_points(
    trigger,
    rate,
    *,
    max_error_db=0.3,
    min_gap_s=0.05,
    **kwargs,
):
    """Simplify the law into ``(frame, dB)`` points on the trigger's clock.

    Ramer-Douglas-Peucker keeps each omitted sample within ``max_error_db``
    of linear interpolation. Nearby points are merged only when that bound
    still holds, so ``min_gap_s`` never sacrifices the error guarantee.
    """
    values = gain_curve_db(trigger, rate, **kwargs)
    if values.size == 0:
        return []
    if max_error_db <= 0 or min_gap_s < 0:
        raise ValueError
    if values.size == 1:
        return [(0, float(values[0]))]

    keep = {0, values.size - 1}
    pending = [(0, values.size - 1)]
    while pending:
        first, last = pending.pop()
        error, index = _segment_error(values, first, last)
        if error > max_error_db:
            keep.add(index)
            pending.append((first, index))
            pending.append((index, last))

    gap = round(float(rate) * min_gap_s)
    ordered = sorted(keep)
    if gap:
        for index in ordered[1:-1]:
            if index not in keep:
                continue
            neighbors = sorted(keep)
            position = neighbors.index(index)
            before, after = neighbors[position - 1], neighbors[position + 1]
            if index - before < gap or after - index < gap:
                error, _ = _segment_error(values, before, after)
                if error <= max_error_db:
                    keep.remove(index)
    return [(index, float(values[index])) for index in sorted(keep)]
