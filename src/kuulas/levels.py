"""Level envelopes per recording (WP36): measure a file once, never again.

``analysis`` needs the mean square of each 20 ms hop of the timeline. The
timeline changes with every edit but the recordings do not, so the
measurement is tied to the *media*: one energy value per small block of the
file (sum of squares of the channel mean), cached by content
(``MediaStore.envelope``). A hop of any clip, wherever an edit has put it, is
then the sum of the blocks it covers, with no audio read.

The block divides the hop, so a clip whose offset and start differ by a
whole number of blocks (every untouched clip, and every cut made on the
block grid, including a ripple delete of whole blocks) composes to exactly
what the audio gives. A cut at any other frame leaves a hop that starts
inside a block; that block is split in proportion to the frames on each
side. With blocks of 1/16 hop or less, that moves a loud hop by well under a
decibel and a quiet one by almost nothing (tested).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

#: Bump when what an envelope holds changes. Part of the cache key.
ALGORITHM = "levels@1"
#: The block is at most this fraction of the hop, as a divisor of the hop.
MAX_BLOCKS_PER_HOP = 16
#: Blocks measured per audio read.
READ_BLOCKS = 4096


def block_frames(hop: int) -> int:
    """The largest divisor of ``hop`` that is at most ``hop / 16`` (60 for the
    960-frame hop of 48 kHz), so hop edges fall on block edges."""
    limit = max(1, hop // MAX_BLOCKS_PER_HOP)
    return next(b for b in range(limit, 0, -1) if hop % b == 0)


def block_energy(read: Callable[[int, int], np.ndarray], frames: int,
                 block: int) -> np.ndarray:
    """Sum of squares of the channel mean per ``block`` frames, float64.

    ``read(first, count)`` gives ``(channels, count)`` samples. The mean is
    taken in float32 and squared in float64, as the timeline path does.
    """
    n = -(-frames // block)
    out = np.zeros(n, dtype=np.float64)
    step = block * READ_BLOCKS
    for first in range(0, frames, step):
        count = min(step, frames - first)
        audio = np.asarray(read(first, count))
        sq = np.square(audio.mean(axis=0, dtype=np.float32).astype(np.float64))
        padded = np.zeros(-(-count // block) * block, dtype=np.float64)
        padded[: sq.shape[0]] = sq
        b0 = first // block
        out[b0:b0 + padded.shape[0] // block] = padded.reshape(-1, block).sum(axis=1)
    return out


def energy_upto(blocks: np.ndarray, block: int, frames: int,
                positions: np.ndarray) -> np.ndarray:
    """Energy from the start of the file to each source frame in ``positions``
    (clamped to the file), splitting the block a position falls in."""
    if blocks.shape[0] == 0:
        return np.zeros(np.shape(positions), dtype=np.float64)
    cum = np.concatenate(([0.0], np.cumsum(blocks)))
    x = np.clip(positions, 0, frames)
    i = x // block
    inside = i < blocks.shape[0]
    j = np.minimum(i, blocks.shape[0] - 1)
    width = np.minimum(block, frames - j * block)
    part = np.where(inside, blocks[j] * (x - j * block) / np.maximum(width, 1), 0.0)
    return cum[np.minimum(i, blocks.shape[0])] + part
