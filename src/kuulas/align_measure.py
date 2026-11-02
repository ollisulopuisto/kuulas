"""Windowed lag measurements between a reference and a candidate signal (WP16).

Pure numpy over low-rate level envelopes (see ``peaks``), never project audio:
each ``window`` of the candidate is slid against the reference within
±``max_lag`` and the normalised correlation peak becomes one measurement
``(time_seconds, lag_seconds, peak_ratio)`` — exactly what
``align_math.fit_drift`` fits. A positive lag means the candidate's content
sits that much later in the reference (the candidate must move right by it).
``peak_ratio`` is the best peak over the second-best outside a ±0.5 s guard,
so an ambiguous window (music, repetition, silence) rates low and
``align_math`` drops it instead of guessing.
"""

from __future__ import annotations

import numpy as np

#: The second peak must be at least this far from the best to count as its own.
_GUARD_SECONDS = 0.5


def _slide_correlation(region: np.ndarray, win: np.ndarray) -> np.ndarray:
    """Normalised correlation of ``win`` at every position inside ``region``."""
    w = win.size
    count = region.size - w + 1
    if count <= 0:
        return np.zeros(0)
    win_z = win - win.mean()
    win_norm = float(np.sqrt((win_z**2).sum()))
    c1 = np.concatenate([[0.0], np.cumsum(region)])
    c2 = np.concatenate([[0.0], np.cumsum(region**2)])
    sums = c1[w:] - c1[:-w]
    sq_sums = c2[w:] - c2[:-w]
    means = sums / w
    var = np.maximum(sq_sums / w - means**2, 0.0)
    conv = np.convolve(region, win[::-1], mode="valid")
    numerator = conv - sums * win.mean()
    # numerator holds dot products of the centred signals; divide by the two
    # norms (the window's sqrt(w) factor turns its variance into the norm).
    denom = np.sqrt(var) * win_norm * np.sqrt(w)
    out = np.zeros(count)
    ok = denom > 1e-12
    out[ok] = numerator[ok] / denom[ok]
    return out


def windowed_lags(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    rate: int,
    window: float,
    hop: float,
    max_lag: float,
) -> list[tuple[float, float, float]]:
    """One ``(time, lag, peak_ratio)`` per candidate window; empty when too short."""
    ref = np.asarray(reference, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    w, h, m = int(window * rate), int(hop * rate), int(max_lag * rate)
    if w <= 0 or ref.size < w or cand.size < w:
        return []
    guard = max(1, int(_GUARD_SECONDS * rate))
    out: list[tuple[float, float, float]] = []
    for start in range(0, cand.size - w + 1, h):
        win = cand[start : start + w]
        if win.std() <= 1e-9:
            continue
        lo = max(0, start - m)
        hi = min(ref.size - w, start + m)
        if hi < lo:
            continue
        corr = _slide_correlation(ref[lo : hi + w], win)
        if corr.size == 0:
            continue
        best = int(np.argmax(corr))
        peak = float(corr[best])
        if peak <= 0.0:
            continue
        masked = corr.copy()
        masked[max(0, best - guard) : best + guard + 1] = -np.inf
        second = float(masked.max()) if np.isfinite(masked).any() else 0.0
        ratio = peak / second if second > 1e-12 else float("inf")
        lag = (lo + best - start) / rate
        out.append(((start + w / 2) / rate, lag, ratio))
    return out
