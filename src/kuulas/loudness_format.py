"""Number formats for a loudness table.

``format_lufs`` renders one loudness value with one decimal and an ASCII
hyphen-minus; ``format_gain`` always shows the sign except for zero;
``format_delta`` renders ``target - measured`` like ``format_gain``;
``level_state`` classifies a measured loudness against a target. Errors are
plain ``ValueError``; there is no user-facing text — numbers and signs only,
labels are the caller's. Inputs are never mutated.
"""

from __future__ import annotations

import math

EN_DASH = "\u2013"


def format_lufs(value: float | None) -> str:
    """Render ``value`` in LUFS with one decimal and an ASCII minus sign.

    Returns the en dash character (U+2013) for None, NaN or -inf. A value
    that rounds to zero is rendered as ``"0.0"``, never ``"-0.0"``.
    """
    if value is None or math.isnan(value) or value == float("-inf"):
        return EN_DASH
    text = f"{value:.1f}"
    if text == "-0.0":
        text = "0.0"
    return text


def format_gain(db: float | None) -> str:
    """Render a gain change in dB, always signed, one decimal.

    Zero — including values that round to zero — is rendered as ``"0.0"``
    without a sign. Returns the en dash character (U+2013) for None, NaN or
    -inf.
    """
    if db is None or math.isnan(db) or db == float("-inf"):
        return EN_DASH
    text = f"{db:+.1f}"
    if text in ("+0.0", "-0.0"):
        text = "0.0"
    return text


def format_delta(measured: float | None, target: float) -> str:
    """Render ``target - measured`` like :func:`format_gain`.

    Returns the en dash character (U+2013) when ``measured`` is None, NaN or
    -inf.
    """
    if measured is None or math.isnan(measured) or measured == float("-inf"):
        return EN_DASH
    return format_gain(target - measured)


def level_state(
    measured: float | None, target: float, tolerance: float = 1.0
) -> str:
    """Classify ``measured`` against ``target`` within ``tolerance`` dB.

    Returns ``"silent"`` for None, NaN or -inf, ``"ok"`` when the distance is
    within tolerance (boundary included), ``"low"`` when measured is more than
    tolerance below the target, and ``"high"`` when more than tolerance above.
    ``tolerance`` below 0 raises ``ValueError``.
    """
    if tolerance < 0.0:
        msg = f"tolerance must not be negative, got {tolerance!r}"
        raise ValueError(msg)
    if measured is None or math.isnan(measured) or measured == float("-inf"):
        return "silent"
    diff = target - measured
    if abs(diff) <= tolerance:
        return "ok"
    return "low" if diff > 0 else "high"
