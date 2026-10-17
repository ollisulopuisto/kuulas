"""Level matching for A/B (WP24.2).

Turns the louder of two signals down by their integrated-loudness difference,
so an A/B comparison is not decided by loudness. The quieter side stays at
0.0 dB and the correction never exceeds ``max_db``. Measures integrated
loudness with speechmix's meter; a silent or unmeasurable side yields
``(0.0, 0.0)``.
"""

from __future__ import annotations

import numpy as np
from speechmix.meter import Meter

#: BS.1770 absolute gate: quieter than this is silence.
SILENCE_LUFS = -70.0


def _integrated_loudness(audio: np.ndarray, rate: int) -> float:
    """Integrated loudness of ``(channels, samples)`` audio in LUFS.

    Returns ``-inf`` when nothing can be measured (silence, or too short).
    """
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    meter = Meter(rate)
    value = meter.integrated_loudness(x.T)
    return float("-inf") if value is None else float(value)


def match_gains(
    a: np.ndarray, b: np.ndarray, rate: int, max_db: float = 12.0
) -> tuple[float, float]:
    """Return ``(gain_a_db, gain_b_db)`` for matching ``a`` and ``b`` in level.

    The louder side is turned down by the loudness difference, capped at
    ``max_db``; the quieter side stays at ``0.0``. A silent side (quieter than
    -70 LUFS) or one too short to measure yields ``(0.0, 0.0)``.
    """
    loud_a = _integrated_loudness(a, rate)
    loud_b = _integrated_loudness(b, rate)
    if loud_a < SILENCE_LUFS or loud_b < SILENCE_LUFS:
        return (0.0, 0.0)
    diff = loud_a - loud_b
    if diff > 0:
        return (-min(diff, max_db), 0.0)
    if diff < 0:
        return (0.0, -min(-diff, max_db))
    return (0.0, 0.0)
