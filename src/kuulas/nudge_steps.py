"""Nudge step sizes for moving clips by small time amounts.

The keymap nudges clips earlier or later.  Each nudge uses a step size that
depends on the modifier keys: fine (1 ms), normal (10 ms), coarse (100 ms) or
second (1 s).  The step is rounded to the nearest whole frame at the project
rate, but is always at least one frame.
"""

from __future__ import annotations

from kuulas.messages import KuulasError

LEVELS = ("fine", "normal", "coarse", "second")

_SECONDS: dict[str, float] = {
    "fine": 0.001,
    "normal": 0.01,
    "coarse": 0.1,
    "second": 1.0,
}


def nudge_frames(rate: int, level: str) -> int:
    """Return the whole-frame step size for ``level`` at ``rate``.

    Levels are ``"fine"`` (1 ms), ``"normal"`` (10 ms), ``"coarse"``
    (100 ms) and ``"second"`` (1 s).  The result is ``round(rate * seconds)``
    but never less than one frame.
    """
    if level not in _SECONDS:
        raise KuulasError("error.nudge_steps.unknown_level", level=level)
    return max(1, round(rate * _SECONDS[level]))


def level_for(*, shift: bool, alt: bool) -> str:
    """Return the level implied by modifier keys.

    No modifier means ``"normal"``; Shift means ``"coarse"``; Alt means
    ``"fine"``; Shift+Alt means ``"second"``.
    """
    if shift and alt:
        return "second"
    if shift:
        return "coarse"
    if alt:
        return "fine"
    return "normal"


def next_level(level: str, direction: str) -> str:
    """Step ``level`` up or down the ladder.

    The ladder is ``fine``, ``normal``, ``coarse``, ``second``.  Moving past
    either end keeps the level at that end.
    """
    try:
        index = LEVELS.index(level)
    except ValueError as exc:
        raise KuulasError("error.nudge_steps.unknown_level", level=level) from exc

    if direction == "up":
        return LEVELS[min(index + 1, len(LEVELS) - 1)]
    if direction == "down":
        return LEVELS[max(index - 1, 0)]
    raise KuulasError("error.nudge_steps.unknown_direction", direction=direction)
