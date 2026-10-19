"""JKL shuttle key logic (WP26).

Maps the standard JKL transport keys to signed playback speeds and decides
which scrub style the engine should use for a given speed.
"""

from __future__ import annotations

from kuulas.messages import KuulasError

LADDER = (1.0, 1.5, 2.0, 3.0, 5.0)
"""Positive shuttle speeds, from slowest to fastest."""

STEP_MS = 10
"""Tap-step length for held scrubbing."""


SLOW_SPEEDS = (0.25, 0.5, 0.75)
"""Speeds for slow hold-to-play listening (Shift+J / Shift+L), a preference."""

DEFAULT_SLOW = 0.5


def slow_hold_speed(direction: str, setting: float | None = DEFAULT_SLOW) -> float:
    """Signed tape speed while Shift+L (``"l"``) or Shift+J (``"j"``) is held.

    ``setting`` outside ``SLOW_SPEEDS`` falls back to ``DEFAULT_SLOW``.
    """
    speed = setting if setting in SLOW_SPEEDS else DEFAULT_SLOW
    if direction == "l":
        return speed
    if direction == "j":
        return -speed
    raise _unknown_key(direction)


def _unknown_key(key: str) -> KuulasError:
    return KuulasError("error.shuttle.unknown_key", key=key)


def press(speed: float, key: str) -> float:
    """Return the new signed shuttle speed after pressing ``key``.

    ``key`` is one of ``"j"`` (backward), ``"k"`` (stop) or ``"l"`` (forward).
    ``l`` climbs ``LADDER``; ``j`` climbs its negatives. ``k`` always returns
    ``0.0``.

    The returned speed is always ``0.0``, a value from ``LADDER``, or the
    negation of a value from ``LADDER``.
    """
    if key == "k":
        result = 0.0
    elif key == "l":
        result = _next_ladder(speed, 1)
    elif key == "j":
        result = _next_ladder(speed, -1)
    else:
        raise _unknown_key(key)
    return result


def _next_ladder(speed: float, sign: int) -> float:
    """The next speed in ``sign * LADDER`` from ``speed``."""
    magnitude = abs(speed)
    if sign * speed <= 0.0:
        return sign * LADDER[0]
    for step in LADDER:
        if step > magnitude:
            return sign * step
    return sign * LADDER[-1]


def scrub_style(speed: float) -> str:
    """Return the scrub style for ``speed``.

    ``"tape"`` is variable-rate resampling where pitch follows the speed.
    ``"grains"`` uses 60 ms grains with a skip for faster shuttling.
    """
    return "tape" if abs(speed) <= 2.0 else "grains"


def held_scrub_speed(direction: str) -> float:
    """Return the slow signed speed while holding K and L/J.

    ``direction`` is ``"l"`` for forward or ``"j"`` for backward.
    """
    if direction == "l":
        return 0.25
    if direction == "j":
        return -0.25
    raise _unknown_key(direction)
