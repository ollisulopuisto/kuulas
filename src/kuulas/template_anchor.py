"""Anchor resolution for standing clips in a series template.

A standing clip is placed by an anchor: ``{"from": "start", "offset": s}``
from the programme start, ``{"from": "end", "offset": s}`` so the clip's end
sits ``s`` seconds before the programme end, or
``{"from": "marker", "name": n, "offset": s}`` from a named marker's time.
``resolve_anchor`` returns the clip's start frame (an int, ``round(x * rate)``);
``validate_anchor`` returns a normalised copy of an anchor. Errors are plain
``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

_ANCHORS = ("start", "end", "marker")


def validate_anchor(anchor: dict) -> dict:
    """Return a normalised copy of ``anchor`` without mutating it.

    ``offset`` defaults to ``0.0``. A ``marker`` anchor needs a non-empty
    ``name``. An unknown ``from`` raises ``ValueError``.
    """
    kind = anchor.get("from")
    if kind not in _ANCHORS:
        msg = f"unknown anchor 'from': {kind!r}"
        raise ValueError(msg)
    result = dict(anchor)
    result.setdefault("offset", 0.0)
    if kind == "marker":
        name = result.get("name")
        if not name:
            msg = "a marker anchor needs a non-empty name"
            raise ValueError(msg)
    return result


def resolve_anchor(
    anchor: dict,
    clip_length: float,
    programme_length: float,
    markers: dict[str, float],
    rate: float,
) -> int:
    """Return the clip's start frame for ``anchor``.

    ``start`` places the clip at ``offset * rate``. ``end`` places the clip's
    end ``offset`` seconds before the programme end, clamped at frame 0.
    ``marker`` places it at the named marker's time plus ``offset``, clamped at
    frame 0; an unknown marker raises ``ValueError``.
    """
    if rate <= 0:
        msg = f"rate must be positive, got {rate}"
        raise ValueError(msg)
    if clip_length < 0:
        msg = f"clip_length must not be negative, got {clip_length}"
        raise ValueError(msg)
    if programme_length < 0:
        msg = f"programme_length must not be negative, got {programme_length}"
        raise ValueError(msg)

    anchor = validate_anchor(anchor)
    kind = anchor["from"]
    offset = anchor["offset"]

    if kind == "start":
        seconds = offset
    elif kind == "end":
        seconds = programme_length - clip_length - offset
    else:
        name = anchor["name"]
        if name not in markers:
            msg = f"marker {name!r} is unknown"
            raise ValueError(msg)
        seconds = markers[name] + offset

    if kind == "start":
        return round(seconds * rate)
    return max(0, round(seconds * rate))
