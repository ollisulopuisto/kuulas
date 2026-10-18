"""Clip loudness measurement and gain matching (WP19c)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from speechmix.meter import IntegratedMeter

from .ops import CLIP_GAIN_RANGE

if TYPE_CHECKING:
    from .mixer import Store
    from .model import Clip

#: Silence threshold per BS.1770 absolute gate
SILENCE_LUFS = -70.0

#: Maximum chunk duration read from media store at once (seconds)
CHUNK_SEC = 60


def measure_clip(store: Store, clip: Clip, rate: int) -> float | None:
    """Integrated loudness of a clip's own audio range in LUFS.

    Reads in chunks of at most 60 seconds and feeds the integrated meter
    incrementally without loading the entire audio into memory.
    Returns None if quieter than -70 LUFS, shorter than the meter minimum,
    or not finite.
    """
    if clip.length <= 0:
        return None

    meter = IntegratedMeter(rate)
    chunk_step = CHUNK_SEC * rate
    pos = clip.offset
    end = clip.offset + clip.length

    while pos < end:
        count = min(chunk_step, end - pos)
        chunk = store.read(clip.media, pos, count)
        meter.add(chunk)
        pos += count

    value = meter.value()
    if value is None or not math.isfinite(value) or value < SILENCE_LUFS:
        return None
    return float(value)


def gain_to_target(
    measured_lufs: float | None, target_lufs: float | None
) -> float | None:
    """Return gain correction in dB to reach target_lufs from measured_lufs.

    Capped to the range accepted by ops.set_clip (ops.CLIP_GAIN_RANGE).
    Returns None if either argument is None.
    """
    if measured_lufs is None or target_lufs is None:
        return None
    delta = float(target_lufs) - float(measured_lufs)
    low, high = CLIP_GAIN_RANGE
    return max(low, min(high, delta))
