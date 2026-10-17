"""Typed time parsing for spot / goto dialogs (WP19f).

A spot is either an absolute timecode ("go to 1:02:03.500") or a relative
offset ("move +1.5 seconds"). The parser returns a frame count at the given
sample rate; ``spot_delta`` turns that into the shift to apply to a clip.
"""

from __future__ import annotations

from dataclasses import dataclass

from kuulas.messages import KuulasError


@dataclass(frozen=True)
class Spot:
    """A parsed spot: absolute timecode or relative offset, in frames."""

    kind: str
    frames: int


def _invalid(text: str) -> KuulasError:
    return KuulasError("error.spot.invalid", text=text)


def _parse_absolute(text: str, rate: int) -> Spot:
    """Parse ``text`` as an absolute timecode and return the frame."""
    # Finnish users may type a decimal comma; the rest of the code wants a dot.
    normalised = text.replace(",", ".")
    parts = normalised.split(":")
    if len(parts) > 3:
        raise _invalid(text)

    try:
        if len(parts) == 1:
            seconds = float(parts[0])
        elif len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            if minutes < 0 or seconds < 0 or seconds >= 60:
                raise _invalid(text)
            seconds = minutes * 60 + seconds
        else:  # len(parts) == 3
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            if hours < 0 or minutes < 0 or seconds < 0:
                raise _invalid(text)
            if minutes >= 60 or seconds >= 60:
                raise _invalid(text)
            seconds = hours * 3600 + minutes * 60 + seconds
    except ValueError as exc:
        raise _invalid(text) from exc

    if seconds < 0:
        raise _invalid(text)

    return Spot("absolute", round(seconds * rate))


def _parse_relative(text: str, rate: int) -> Spot:
    """Parse ``text`` as a signed offset and return the frame offset."""
    sign = 1 if text[0] == "+" else -1
    rest = text[1:]
    if not rest:
        raise _invalid(text)

    if rest[-1].lower() == "s":
        try:
            seconds = float(rest[:-1])
        except ValueError as exc:
            raise _invalid(text) from exc
    else:
        try:
            milliseconds = float(rest)
        except ValueError as exc:
            raise _invalid(text) from exc
        seconds = milliseconds / 1000

    return Spot("relative", round(seconds * rate) * sign)


def parse_spot(text: str, rate: int) -> Spot:
    """Parse a typed time into a :class:`Spot`.

    Accepted absolute forms (surrounding spaces are ignored):

    - ``1:02:03.500`` and ``1:02:03,500`` (hours : minutes : seconds)
    - ``2:03`` (minutes : seconds)
    - ``62.5`` (seconds)

    Accepted relative forms (signed offsets):

    - ``+120`` and ``-120`` (milliseconds)
    - ``+1.5s`` and ``-0.5s`` (seconds)

    Anything else raises :class:`KuulasError` with the key
    ``error.spot.invalid``.
    """
    stripped = text.strip()
    if not stripped:
        raise _invalid(text)

    if stripped[0] in "+-":
        return _parse_relative(stripped, rate)

    return _parse_absolute(stripped, rate)


def spot_delta(spot: Spot, current_frame: int, playhead_frame: int) -> int:  # noqa: ARG001 - reserved for future UI context
    """Return the frame shift to apply for ``spot``.

    An absolute spot means "make ``current_frame`` become the spot", so the
    returned delta is ``spot.frames - current_frame``. A relative spot means
    "move by the offset", so the delta is ``spot.frames``.

    ``playhead_frame`` is part of the public signature for future UI context
    but is not used by the current logic.
    """
    if spot.kind == "absolute":
        return spot.frames - current_frame
    return spot.frames
