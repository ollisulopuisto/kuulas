"""The peak pyramid: waveform overviews computed once per recording (WP36).

Min/max per 256, 1024, 4096, 16384 and 65536 frames of the channel mean,
built when a file is imported and kept in ``caches/peaks/``, keyed by the
media's SHA-256 and this algorithm's version, so no edit ever invalidates
them. The UI draws from binary tiles of a level; ``tile`` returns one as
bytes together with its ``ETag`` (the HTTP endpoint is WP3). The tag is a
function of the cache key, level and tile alone, so the browser may keep a
tile for good: when the audio or the algorithm changes, the key does.

A level groups the finest peaks, so its last peak covers a short tail
padded with silence, as ``MediaStore.peaks`` always did.
"""

from __future__ import annotations

import hashlib
import itertools

import numpy as np

from . import caches
from .messages import KuulasError

#: Bump when what the pyramid holds changes. Part of every key and ETag.
ALGORITHM = "peaks-pyramid@1"
#: Frames per peak, finest first. The first is the base ``media.PEAK_FRAMES``.
LEVELS = (256, 1024, 4096, 16384, 65536)
#: Peaks per tile: 2048 float32 values, 8 KB, about 10 s at the finest level.
TILE_PEAKS = 1024


class PeakError(KuulasError, ValueError):
    """A tile that does not exist was asked for."""


def pyramid_key(digest: str, rate: int) -> str:
    """Raises ``caches.CacheKeyError`` when ``digest`` is not a content hash."""
    return caches.key([digest], {"rate": rate, "levels": list(LEVELS)}, ALGORITHM)


def build(base: np.ndarray) -> dict[int, np.ndarray]:
    """Every level from the finest peaks (``(n, 2)`` min/max per 256 frames)."""
    out = {LEVELS[0]: np.asarray(base, dtype=np.float32)}
    for finer, coarser in itertools.pairwise(LEVELS):
        k = coarser // finer
        prev = out[finer]
        n = int(np.ceil(prev.shape[0] / k))
        grouped = np.zeros((n * k, 2), dtype=np.float32)
        grouped[: prev.shape[0]] = prev
        grouped = grouped.reshape(n, k, 2)
        out[coarser] = np.stack(
            [grouped[:, :, 0].min(axis=1), grouped[:, :, 1].max(axis=1)], axis=1)
    return out


def save(target, levels: dict[int, np.ndarray]) -> None:
    caches.write_atomic(
        target, lambda f: np.savez(f, **{f"l{lvl}": a for lvl, a in levels.items()}))


def load(source) -> dict[int, np.ndarray]:
    """Raises ``OSError``/``ValueError`` when the file is missing or damaged."""
    with np.load(source) as z:
        levels = {lvl: z[f"l{lvl}"] for lvl in LEVELS}
    if any(a.ndim != 2 or a.shape[1] != 2 for a in levels.values()):
        raise PeakError("error.peaks.damaged")
    return levels


def tile_count(peaks_in_level: int) -> int:
    return max(1, -(-peaks_in_level // TILE_PEAKS))


def tile(levels: dict[int, np.ndarray], cache_key: str, level: int,
         index: int) -> tuple[bytes, str]:
    """``(bytes, etag)``: min/max pairs as little-endian float32, interleaved."""
    if level not in levels:
        raise PeakError("error.peaks.no_level", level=level,
                        levels=", ".join(str(lvl) for lvl in LEVELS))
    data = levels[level]
    if not 0 <= index < tile_count(data.shape[0]):
        raise PeakError("error.peaks.no_tile", level=level, tile=index)
    body = np.ascontiguousarray(
        data[index * TILE_PEAKS:(index + 1) * TILE_PEAKS], dtype="<f4").tobytes()
    tag = hashlib.sha256(f"{cache_key}/{level}/{index}".encode()).hexdigest()[:32]
    return body, f'"{tag}"'
