"""The level of a clipboard preview (WP82): pure arithmetic, no audio, no files.

Pasted material (a clip from elsewhere at about -14 LUFS) is far louder than a
quietly recorded session. The preview is therefore turned down to the project's
own level, never up, and passes a soft limiter so a peak cannot jump out. Only
the preview is changed; the pasted audio and the project's mix are not.
"""

from __future__ import annotations

import math

import numpy as np

#: Reference when the project has nothing to measure (empty or silent), LUFS.
DEFAULT_REFERENCE_LUFS = -23.0
#: Rough distance from a speech signal's sample peak down to its integrated
#: loudness; only used when there is no loudness number, only a peak.
PEAK_TO_LUFS_DB = 14.0
#: The preview never peaks above this, dBFS.
CEILING_DB = -1.0
#: The limiter starts to bend at this fraction of the ceiling (linear).
KNEE = 0.7


def reference_lufs(speech_lufs: list[float | None], peak_db: float | None) -> float:
    """The project's reference level: the power average of its speech tracks'
    loudness; else from the project's peak; else the conservative default."""
    levels = [v for v in speech_lufs if v is not None and math.isfinite(v)]
    if levels:
        power = sum(10.0 ** (v / 10.0) for v in levels) / len(levels)
        return 10.0 * math.log10(power)
    if peak_db is not None and math.isfinite(peak_db):
        return peak_db - PEAK_TO_LUFS_DB
    return DEFAULT_REFERENCE_LUFS


def preview_gain_db(reference: float, entry_lufs: float | None, *,
                    entry_peak_db: float | None = None,
                    project_peak_db: float | None = None) -> float:
    """The preview's gain in dB, 0 or negative (attenuation only).

    Loudness decides; when the entry has no loudness (too short) its peak
    stands in. The peak guard also keeps the entry's peak under the project's.
    """
    if entry_lufs is None and entry_peak_db is not None:
        entry_lufs = entry_peak_db - PEAK_TO_LUFS_DB
    gain = 0.0 if entry_lufs is None else min(0.0, reference - entry_lufs)
    if entry_peak_db is not None and project_peak_db is not None:
        gain = min(gain, project_peak_db - entry_peak_db)
    return min(0.0, gain)


def soft_limit(block: np.ndarray, ceiling_db: float = CEILING_DB) -> np.ndarray:
    """A memoryless soft limiter: linear up to ``KNEE * ceiling``, then a tanh
    bend that tends to the ceiling and never passes it. Returns a new array."""
    ceiling = 10.0 ** (ceiling_db / 20.0)
    knee = KNEE * ceiling
    mag = np.abs(block)
    over = mag > knee
    if not over.any():
        return block
    room = ceiling - knee
    bent = knee + room * np.tanh((mag - knee) / room)
    return np.where(over, np.sign(block) * bent, block).astype(block.dtype)
