"""Bounded source reads for automatic-sync analysis workers, without edits."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from . import priority
from .align_errors import SyncError
from .align_sound import ENVELOPE_RATE, envelope


def read_envelope(read: Callable[[int, int], np.ndarray], *, rate: int,
                  start: int, frames: int, chunk_seconds: int = 10,
                  max_seconds: int = 4 * 3600) -> np.ndarray:
    """Read one source span as channel-first chunks; retain only a 1 kHz envelope.

    ``read`` is a worker's streaming MediaStore reader bound to a media id.
    The worker must validate media availability before this call: padded zero
    reads are silence, not evidence that an offline source is online. The
    duration cap bounds retained envelope memory; chunk size bounds PCM memory.
    A partial final millisecond is ignored, as in ``align_sound.envelope``.
    """
    values = (rate, start, frames, chunk_seconds, max_seconds)
    if (any(type(v) is not int for v in values) or rate < ENVELOPE_RATE
            or rate % ENVELOPE_RATE or start < 0 or frames < 0
            or not 1 <= chunk_seconds <= 60 or max_seconds <= 0
            or frames > max_seconds * rate):
        raise SyncError("error.sync.range")
    block = rate // ENVELOPE_RATE
    usable = frames // block * block
    result = np.empty(usable // block, dtype=np.float64)
    chunk = chunk_seconds * rate
    for first in range(0, usable, chunk):
        priority.checkpoint()
        count = min(chunk, usable - first)
        data = read(start + first, count)
        if (data.ndim != 2 or data.shape[1] != count
                or not 1 <= data.shape[0] <= 64):
            raise SyncError("error.sync.source")
        values = envelope(data.T, rate)
        at = first // block
        result[at:at + values.size] = values
    return result
