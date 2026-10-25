"""Pure cart timing and gain; no files or audio devices."""

from __future__ import annotations

import math

from .preview_level import CEILING_DB, PEAK_TO_LUFS_DB


def trimmed_length(start: int, length: int, stop: int) -> int:
    """Never extend a logged clip. A stop at/before start retains one frame."""
    return max(1, min(length, stop - start))


def cart_gain_db(voice: float | None, entry: float | None, peak: float | None,
                 trim: float = 0, *, reference: float) -> float:
    """Match digital voice loudness, then manual trim, with a -1 dBTP ceiling.

    Unknown entry peaks cannot safely be boosted. A short entry without LUFS
    uses the same peak-to-loudness approximation as preview_level.
    """
    target = voice if voice is not None and math.isfinite(voice) else reference
    if entry is None or not math.isfinite(entry):
        entry = peak - PEAK_TO_LUFS_DB if peak is not None else target
    gain = target - entry + trim
    ceiling = CEILING_DB - peak if peak is not None and math.isfinite(peak) else 0
    return min(gain, ceiling)
