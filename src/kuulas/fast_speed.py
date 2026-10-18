"""Fast listening speed state (WP26, "Sped-up listening").

Pure state, no audio. Fast listening is a **toggle** between normal speed and
a chosen speed; the chosen speed is **stepless** from 1.0x to 2.0x (owner,
2026-10-18: "portaaton"), nudged 0.05x at a time or set from a slider, and
the pitch is kept (``stretch.py``). The playback engine plays at
``effective(state)``; the UI shows ``chip_text(state, lang)``.
``ui/fast-speed.js`` is a port of this module; both read
``ui/tests/fixtures/fast-speed-cases.json``, so they cannot drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from .messages import t

#: The fastest chosen speed. Beyond it the JKL shuttle (tape speed) takes over.
MAX_FAST = 2.0
#: The slowest chosen speed: 1.0 is normal, so the slider's left end is "no
#: faster than normal".
MIN_FAST = 1.0
#: One key press or slider tick. Fine enough to feel stepless, coarse enough
#: that 20 presses cover the range.
STEP = 0.05
#: What the toggle turns on when the chosen speed is 1.0 (it would do nothing).
DEFAULT_FAST = 1.5

_QUANTUM = Decimal("0.05")


@dataclass(frozen=True)
class FastState:
    """The chosen fast speed and whether fast listening is switched on."""

    fast: float = DEFAULT_FAST
    active: bool = False


def effective(state: FastState) -> float:
    """The speed to play at: normal when off, the chosen speed when on."""
    return state.fast if state.active else 1.0


def _snap(speed: float) -> float:
    """The nearest multiple of ``STEP``, so repeated steps never drift."""
    steps = (Decimal(str(speed)) / _QUANTUM).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return float(steps * _QUANTUM)


def _clamp(speed: float) -> float:
    return max(MIN_FAST, min(MAX_FAST, _snap(speed)))


def toggle(state: FastState) -> FastState:
    """Switch fast listening on or off. Switching on at a chosen speed of 1.0
    (which would sound the same) uses ``DEFAULT_FAST``."""
    if state.active:
        return replace(state, active=False)
    fast = state.fast if state.fast > MIN_FAST else DEFAULT_FAST
    return replace(state, fast=fast, active=True)


def step_up(state: FastState) -> FastState:
    """Raise the chosen speed by ``STEP``, at most ``MAX_FAST``. Whether fast
    listening is on stays as it is."""
    return replace(state, fast=_clamp(state.fast + STEP))


def step_down(state: FastState) -> FastState:
    """Lower the chosen speed by ``STEP``, at least ``MIN_FAST``."""
    return replace(state, fast=_clamp(state.fast - STEP))


def set_fast(state: FastState, value: float) -> FastState:
    """Set the chosen speed directly (the slider): snapped and clamped."""
    return replace(state, fast=_clamp(value))


def reset(state: FastState) -> FastState:  # noqa: ARG001 - same shape as the others
    """Back to normal: the chosen speed 1.0 and fast listening off."""
    return FastState(fast=MIN_FAST, active=False)


def chip_text(state: FastState, lang: str) -> str:
    """The chip label for the current effective speed, or ``""`` at 1.0:
    exact to the step ("1.35x", "1,35x" in Finnish, "1.5x" not "1.50x").

    ``lang`` is ``"en"`` or ``"fi"``; the decimal separator follows the
    language, and the unit suffix is read from the locale catalog.
    """
    speed = effective(state)
    if speed == 1.0:
        return ""
    separator = "," if lang == "fi" else "."
    value = f"{speed:.2f}".rstrip("0").rstrip(".").replace(".", separator)
    return t("format.speed", value=value)
