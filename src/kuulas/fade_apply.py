"""Fades per speaker from a fade plan.

``fades_per_speaker`` groups the fade entries planned by ``plan_fades`` per
speaker. ``fade_lengths`` converts fade times to whole frames at a sample
rate. Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

_KINDS = {"crossfade", "cut", "overlap"}


def fades_per_speaker(plan: list[dict]) -> dict[str, list[dict]]:
    """Group fade entries by speaker.

    Each ``"crossfade"`` or ``"cut"`` entry gives the ``"from"`` speaker an
    ``"out"`` fade and the ``"to"`` speaker an ``"in"`` fade. ``"overlap"``
    entries (talk-overs, all times ``None``) give nothing. A fade whose
    ``end`` is not after its ``start`` is skipped. Each speaker's fades are
    returned sorted by ``start``. The input is not mutated.
    """
    result: dict[str, list[dict]] = {}
    for entry in plan:
        kind = entry["kind"]
        if kind not in _KINDS:
            msg = f"unknown fade kind {kind!r}"
            raise ValueError(msg)
        if kind == "overlap":
            continue
        for speaker, side, start, end in (
            (entry["from"], "out", entry["out_start"], entry["out_end"]),
            (entry["to"], "in", entry["in_start"], entry["in_end"]),
        ):
            if start is None or end is None or end <= start:
                continue
            result.setdefault(speaker, []).append(
                {"side": side, "start": start, "end": end}
            )
    for fades in result.values():
        fades.sort(key=lambda fade: fade["start"])
    return result


def fade_lengths(fades: list[dict], rate: float) -> list[dict]:
    """Convert fade times to whole frames at ``rate``.

    ``start`` and ``end`` become ``round(x * rate)`` integers and a ``"length"``
    of ``end - start`` frames (at least 1) is added. New dicts are returned;
    the input is not mutated.
    """
    if rate <= 0:
        msg = f"rate must be positive, got {rate}"
        raise ValueError(msg)
    result: list[dict] = []
    for fade in fades:
        start = round(fade["start"] * rate)
        end = round(fade["end"] * rate)
        length = end - start
        length = max(length, 1)
        result.append(
            {"side": fade["side"], "start": start, "end": end, "length": length}
        )
    return result
