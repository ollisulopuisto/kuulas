"""Gain suggestions toward a target loudness.

``suggest_gain`` suggests a gain change (in dB) that moves a measured
loudness toward a target, limited by a maximum boost and cut and a tolerance
around the target. ``suggest_all`` applies it to a list of measured items.
Errors are plain ``ValueError``; there is no user-facing text. Inputs are
never mutated.
"""

from __future__ import annotations

import math


def suggest_gain(
    measured_lufs: float | None,
    target_lufs: float,
    max_boost: float = 12.0,
    max_cut: float = 24.0,
    tolerance: float = 1.0,
) -> dict[str, float | bool]:
    """Suggest a gain change in dB to reach ``target_lufs`` from ``measured_lufs``.

    The wanted change is ``target_lufs - measured_lufs``. When its absolute
    value is within ``tolerance`` (boundary included) the suggestion is 0.0
    with ``within_tolerance`` true. Otherwise the wanted change is limited to
    ``[-max_cut, +max_boost]`` and ``clamped`` is true when a limit changed it.
    Results are rounded to 0.1 dB with Python's ``round(x, 1)``.

    A ``measured_lufs`` of None, NaN or -inf (silence) means nothing can be
    suggested: gain 0.0, ``clamped`` and ``within_tolerance`` false.

    ``max_boost``, ``max_cut`` or ``tolerance`` below 0 raises ``ValueError``.
    """
    if max_boost < 0.0:
        msg = f"max_boost must not be negative, got {max_boost!r}"
        raise ValueError(msg)
    if max_cut < 0.0:
        msg = f"max_cut must not be negative, got {max_cut!r}"
        raise ValueError(msg)
    if tolerance < 0.0:
        msg = f"tolerance must not be negative, got {tolerance!r}"
        raise ValueError(msg)

    if (
        measured_lufs is None
        or math.isnan(measured_lufs)
        or measured_lufs == float("-inf")
    ):
        return {"gain_db": 0.0, "clamped": False, "within_tolerance": False}

    wanted = target_lufs - measured_lufs
    if abs(wanted) <= tolerance:
        return {"gain_db": 0.0, "clamped": False, "within_tolerance": True}

    gain = min(max(wanted, -max_cut), max_boost)
    return {
        "gain_db": round(gain, 1),
        "clamped": gain != wanted,
        "within_tolerance": False,
    }


def suggest_all(
    entries: list[dict[str, float | str | None]], tolerance: float = 1.0
) -> dict[str, dict[str, float | bool]]:
    """Suggest a gain for each entry, keyed by its ``id`` in entry order.

    Each entry is ``{"id": ..., "measured": ..., "target": ...}`` and is
    passed to ``suggest_gain`` with the given ``tolerance``. A duplicate id
    raises ``ValueError``.
    """
    result: dict[str, dict[str, float | bool]] = {}
    for entry in entries:
        entry_id = entry["id"]
        if entry_id in result:
            msg = f"duplicate id: {entry_id!r}"
            raise ValueError(msg)
        result[entry_id] = suggest_gain(
            entry["measured"], entry["target"], tolerance=tolerance
        )
    return result
