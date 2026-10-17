"""Fast listening speed state (WP26, "Sped-up listening").

Pure state, no audio: the playback engine will read ``effective(state)`` when
fast listening is active and the UI will show ``chip_text(state, lang)``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal

from .messages import t

#: The fastest fast-listening speed. Above this, the engine uses JKL scrub.
MAX_FAST = 3.0
#: The slowest useful fast-listening speed; 1.0 is normal and needs no chip.
MIN_FAST = 1.1
#: Step size for Shift+. and Alt+.
STEP = 0.1


@dataclass(frozen=True)
class FastState:
    """User-chosen fast speed and whether it is currently active."""

    fast: float = 1.5
    active: bool = False


def effective(state: FastState) -> float:
    """The speed to play at: normal when inactive, ``state.fast`` otherwise."""
    return state.fast if state.active else 1.0


def _round(speed: float) -> float:
    """Round to one decimal place so repeated 0.1 steps never drift."""
    return float(Decimal(str(speed)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _clamp(speed: float) -> float:
    return max(MIN_FAST, min(MAX_FAST, _round(speed)))


def toggle(state: FastState) -> FastState:
    """Switch fast listening on or off."""
    return replace(state, active=not state.active)


def step_up(state: FastState) -> FastState:
    """Increase fast speed by 0.1, clamped to ``MAX_FAST``."""
    return replace(state, fast=_clamp(state.fast + STEP))


def step_down(state: FastState) -> FastState:
    """Decrease fast speed by 0.1, clamped to ``MIN_FAST``."""
    return replace(state, fast=_clamp(state.fast - STEP))


def set_fast(state: FastState, value: float) -> FastState:
    """Set fast speed directly, clamped and rounded to one decimal."""
    return replace(state, fast=_clamp(value))


def chip_text(state: FastState, lang: str) -> str:
    """The chip label for the current effective speed, or ``""`` at 1.0.

    ``lang`` is ``"en"`` or ``"fi"``; the decimal separator follows the
    language, and the unit suffix is read from the locale catalog.
    """
    speed = effective(state)
    if speed == 1.0:
        return ""
    separator = "," if lang == "fi" else "."
    value = f"{speed:.1f}".replace(".", separator)
    return t("format.speed", value=value)
