"""Automatic sync measurements on 1 ms RMS envelopes, independent of the edit.

The coarse pass searches the entire reference for every window, not just the
common prefix. A short local can begin anywhere in an hour-long call, and a
skipped interval can change its offset halfway through. A bounded fine pass
then measures milliseconds. No edit or resampling happens here.
"""

from __future__ import annotations

import numpy as np

from . import priority
from .align_measure import _slide_correlation

ENVELOPE_RATE = 1000
_MIN_CORRELATION = 0.35
_MIN_RATIO = 1.5


def envelope(audio: np.ndarray, rate: int) -> np.ndarray:
    """RMS per millisecond, combining channel power, never cancelling stereo.

    Project audio uses an integer number of frames per millisecond. Reject a
    different rate rather than silently changing the measurement time base.
    """
    data = np.asarray(audio, dtype=np.float64)
    if (not isinstance(rate, int) or rate < ENVELOPE_RATE
            or rate % ENVELOPE_RATE or data.ndim not in (1, 2)
            or not np.isfinite(data).all()):
        raise ValueError("expected finite project audio at an integer kHz rate")
    if data.ndim == 2:
        if data.shape[1] == 0:
            return np.empty(0)
        power = (data * data).mean(axis=1)
    else:
        power = data * data
    block = rate // ENVELOPE_RATE
    n = power.size // block
    if n == 0:
        return np.empty(0)
    return np.sqrt(power[:n * block].reshape(n, block).mean(axis=1))


def _match(reference, window, low, high, rate):
    """Best start with absolute and competing-peak confidence, or None."""
    low, high = max(0, low), min(reference.size - window.size, high)
    if high < low or window.std() <= 1e-9:
        return None
    corr = _slide_correlation(reference[low:high + window.size], window)
    best = int(np.argmax(corr))
    peak = float(corr[best])
    if peak < _MIN_CORRELATION:
        return None
    guard = max(1, round(.5 * rate))
    corr[max(0, best - guard):best + guard + 1] = -np.inf
    second = max(0.0, float(corr.max()))
    ratio = peak / second if second > 1e-12 else 1e9
    if ratio < _MIN_RATIO:
        return None
    return low + best, ratio


def measure(reference: np.ndarray, candidate: np.ndarray
            ) -> list[tuple[float, float, float]]:
    """Clear (candidate time, lag, peak ratio) measurements in seconds.

    Inputs are 1 kHz envelopes from ``envelope``. Positive lag means the
    candidate's content is later in the reference. Require several independent
    windows before deciding on an edit; a single measurement is not a plan.
    """
    ref = np.asarray(reference, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    if (ref.ndim != 1 or cand.ndim != 1 or not np.isfinite(ref).all()
            or not np.isfinite(cand).all()):
        raise ValueError("expected finite one-dimensional envelopes")
    window = min(10_000, min(ref.size, cand.size) // 3)
    window -= window % 10
    if window < 3000:
        return []
    # Decimate block averages rather than samples so a narrow transient is not lost.
    coarse_ref = ref[:ref.size // 10 * 10].reshape(-1, 10).mean(axis=1)
    coarse_cand = cand[:cand.size // 10 * 10].reshape(-1, 10).mean(axis=1)
    hop = max(window, (cand.size - window) // 12 // 10 * 10)
    starts = sorted({*range(0, cand.size - window + 1, hop),
                     (cand.size - window) // 10 * 10})
    points = []
    for start in starts:
        priority.checkpoint()
        rough = _match(coarse_ref, coarse_cand[start // 10:(start + window) // 10],
                       0, coarse_ref.size, 100)
        if rough is None:
            continue
        coarse_at, ratio = rough
        at = coarse_at * 10
        fine = _match(ref, cand[start:start + window], at - 30, at + 30, ENVELOPE_RATE)
        if fine is None:
            continue
        position, _ = fine
        points.append(((start + window / 2) / ENVELOPE_RATE,
                       (position - start) / ENVELOPE_RATE, ratio))
    return points
