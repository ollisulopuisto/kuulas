"""A series template built from what a project holds (WP66), logic only.

``build_template`` takes the project's tracks and buses and the standing
clips the user picked — clip positions in frames at ``rate`` — and returns
the plain dict ``validate_template`` in ``kuulas.template_schema`` accepts
(this module does not import it): ``{"version": 1, "name", "tracks",
"buses", "clips"}``, everything in the order it was given. A picked clip
becomes a reference to its recording with a length in float seconds and an
anchor: a clip whose end sits within one second of the programme end (or
past it) is anchored from the end, so it follows the programme's length;
everything else is anchored from the start.

Pure Python, stdlib only, no kuulas imports, no I/O. Errors are plain
``ValueError`` with no user-facing text. No input is ever touched.
"""

from __future__ import annotations

#: How close (in seconds) a clip's end must sit to the programme end to be
#: anchored from the end. The boundary counts: a gap of exactly this many
#: seconds still anchors from the end.
_END_WINDOW_S = 1.0


def build_template(
    name: str,
    tracks: list[dict],
    buses: list[str],
    chosen: list[dict],
    programme_length: float,
    rate: float,
) -> dict:
    """Return the series template dict for these tracks, buses and clips.

    ``tracks`` are ``{"name", "kind", "bus"}`` dicts (``bus`` a bus name or
    ``None``; a missing ``bus`` key means ``None``, the normalisation
    ``validate_template`` makes), ``buses`` a list of bus names, ``chosen``
    the picked standing clips as ``{"track", "media", "start", "length"}``
    with ``start`` and ``length`` in frames, ``programme_length`` in frames
    and ``rate`` in frames per second. Every returned length and anchor
    offset is a float in seconds. Tracks, buses and clips keep their order.

    A clip whose end is within ``_END_WINDOW_S`` of the programme end (or
    past it) gets ``{"from": "end", "offset": max(0.0, gap / rate)}``, where
    ``gap`` is the frames left after the clip; a clip that runs past the
    end clamps to offset 0, the same clamp ``resolve_anchor`` makes when it
    lands. Every other clip gets ``{"from": "start", "offset": start /
    rate}``, unclamped.

    Raises ``ValueError`` when ``name`` is empty once stripped (or not a
    string at all), when ``rate`` is zero or negative, when
    ``programme_length`` is negative, or when a chosen clip sits on a track
    that is not in ``tracks`` — the message names the track, and the first
    such clip in ``chosen`` order is the one reported. Track kinds, unlisted
    buses, duplicate names and non-positive clip lengths are
    ``validate_template``'s checks on the saved file, not this builder's.
    The input lists and dicts are left untouched.
    """
    if not isinstance(name, str) or not name.strip():
        msg = f"template name must not be empty, got {name!r}"
        raise ValueError(msg)
    if rate <= 0:
        msg = f"rate must be positive, got {rate!r}"
        raise ValueError(msg)
    if programme_length < 0:
        msg = f"programme_length must not be negative, got {programme_length!r}"
        raise ValueError(msg)

    track_names = {track["name"] for track in tracks}
    window = rate * _END_WINDOW_S
    clips: list[dict] = []
    for clip in chosen:
        track = clip["track"]
        if track not in track_names:
            msg = f"clip track {track!r} is not one of the template's tracks"
            raise ValueError(msg)
        gap = programme_length - (clip["start"] + clip["length"])
        if gap <= window:
            anchor = {"from": "end", "offset": max(0.0, gap / rate)}
        else:
            anchor = {"from": "start", "offset": clip["start"] / rate}
        clips.append(
            {
                "track": track,
                "media": clip["media"],
                "length": clip["length"] / rate,
                "anchor": anchor,
            }
        )
    return {
        "version": 1,
        "name": name.strip(),
        "tracks": [
            {"name": t["name"], "kind": t["kind"], "bus": t.get("bus")}
            for t in tracks
        ],
        "buses": [{"name": bus} for bus in buses],
        "clips": clips,
    }
