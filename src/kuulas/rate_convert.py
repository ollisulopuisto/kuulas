"""Convert timeline frame positions when the sample rate changes (WP27).

All positions are whole frames at a sample rate. A frame is converted to the
nearest whole frame at the target rate with round-half-up, and spans are
converted edge to edge: the start and the start plus the length are converted
independently, so two clips that touched (end of one equals start of the next)
still touch after the rate change.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

MONO_SUM_DB = -3.0
"""Gain in dB per side when a stereo master is summed to mono, so a centred
voice keeps its loudness."""


def convert_frame(frame: int, old_rate: int, new_rate: int) -> int:
    """Return ``frame`` as the nearest whole frame at ``new_rate``.

    Uses round-half-up for non-negative inputs. Raises ``ValueError`` for a
    negative frame or a non-positive rate.
    """
    if old_rate <= 0 or new_rate <= 0:
        msg = f"sample rates must be positive, got {old_rate} and {new_rate}"
        raise ValueError(msg)
    if frame < 0:
        msg = f"frame must not be negative, got {frame}"
        raise ValueError(msg)
    return math.floor(frame * new_rate / old_rate + 0.5)


def convert_span(
    start: int,
    length: int,
    old_rate: int,
    new_rate: int,
) -> tuple[int, int]:
    """Convert a ``(start, length)`` span edge to edge.

    Returns ``(new_start, new_length)`` where the edges are converted
    independently, so spans that touched or were separated by a gap never
    overlap after the conversion.
    """
    new_start = convert_frame(start, old_rate, new_rate)
    new_end = convert_frame(start + length, old_rate, new_rate)
    return new_start, new_end - new_start


def convert_chain(spans: Iterable[tuple[int, int]],
                  old_rate: int,
                  new_rate: int) -> list[tuple[int, int]]:
    """Convert a list of ``(start, length)`` spans in the same order."""
    return [convert_span(start, length, old_rate, new_rate) for start, length in spans]


def master_gain_db_for_mono() -> float:
    """Return ``MONO_SUM_DB``: the dB per side when a stereo master is summed to mono."""
    return MONO_SUM_DB
