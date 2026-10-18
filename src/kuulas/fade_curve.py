"""Fade curve gains.

``fade_gain`` returns the linear gain of a fade-in at ``position`` frames
into a fade of ``length`` frames for one of several curves. ``fade_out_gain``
is the mirrored fade-out, and ``fade_table`` samples a fade-in at evenly
spaced points. Errors are plain ``ValueError``; there is no user-facing
text. Inputs are never mutated.
"""

from __future__ import annotations

import math

_SHAPES = ("linear", "equal_power", "cosine", "exponential")


def fade_gain(position: float, length: float, shape: str) -> float:
    """Return the fade-in gain at ``position`` of a fade of ``length`` frames.

    ``position`` is clamped to ``[0, length]``, so the gain is 0.0 at the
    start and 1.0 at the end. ``length <= 0`` or an unknown ``shape`` raises
    ``ValueError``.
    """
    if length <= 0:
        msg = f"length must be positive, got {length!r}"
        raise ValueError(msg)
    if shape not in _SHAPES:
        msg = f"unknown fade shape {shape!r}"
        raise ValueError(msg)
    p = min(max(position, 0.0), length)
    t = p / length
    if shape == "linear":
        return t
    if shape == "equal_power":
        return math.sin(t * math.pi / 2.0)
    if shape == "cosine":
        return 0.5 - 0.5 * math.cos(t * math.pi)
    return t * t


def fade_out_gain(position: float, length: float, shape: str) -> float:
    """Return the fade-out gain: ``fade_gain(length - position, length, shape)``."""
    return fade_gain(length - position, length, shape)


def fade_table(length: float, shape: str, points: int) -> list[float]:
    """Return ``points`` evenly spaced fade-in gains from 0.0 to 1.0."""
    if points < 2:
        msg = f"points must be at least 2, got {points!r}"
        raise ValueError(msg)
    return [fade_gain(i * length / (points - 1), length, shape)
            for i in range(points)]
