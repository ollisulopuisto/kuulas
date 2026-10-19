"""Ruler tick steps, times and labels, logic only.

``tick_step`` picks the smallest step from a fixed ladder that is wide enough
on screen, ``tick_times`` lists the ticks in a range and ``tick_label`` writes
one tick's time. Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

import math

_LADDER = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120,
           300, 600, 900, 1800, 3600, 7200)
_MAX_TICKS = 10000


def tick_step(frames_per_pixel: float, rate: float, min_px: float = 80) -> float:
    """The smallest ladder step (seconds) at least ``min_px`` pixels wide."""
    if frames_per_pixel <= 0 or rate <= 0 or min_px <= 0:
        msg = "frames_per_pixel, rate and min_px must be positive"
        raise ValueError(msg)
    for step in _LADDER:
        if step * rate / frames_per_pixel >= min_px:
            return step
    return _LADDER[-1]


def tick_times(start_s: float, end_s: float, step: float) -> list[float]:
    """Tick times in seconds, multiples of ``step`` within ``[start_s, end_s]``."""
    if step <= 0:
        msg = f"step must be positive, got {step!r}"
        raise ValueError(msg)
    if end_s < start_s:
        return []
    first = math.ceil(round(start_s / step, 9))
    last = math.floor(round(end_s / step, 9))
    if last - first + 1 > _MAX_TICKS:
        msg = f"more than {_MAX_TICKS} ticks"
        raise ValueError(msg)
    return [round(k * step, 6) for k in range(first, last + 1)]


def _decimals(step: float) -> int:
    text = f"{step:.6f}".rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0


def tick_label(seconds: float, step: float) -> str:
    """``M:SS`` (``H:MM:SS`` from an hour), with the step's decimals."""
    places = _decimals(step)
    whole = int(seconds)
    fraction = ""
    if places:
        fraction = f"{seconds - whole:.{places}f}"[1:]
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}{fraction}"
    return f"{minutes}:{secs:02d}{fraction}"
