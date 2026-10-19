"""Validation and normalisation of a series template.

Pure logic, stdlib only. ``validate_template`` returns a normalised deep copy
of ``template`` or raises ``ValueError`` naming the field. There is no
user-facing text.
"""

from __future__ import annotations

from kuulas.template_anchor import validate_anchor

_KINDS = ("speech", "music")


def _non_empty_string(value, field):
    if not isinstance(value, str) or not value.strip():
        msg = f"{field} must not be empty"
        raise ValueError(msg)
    return value.strip()


def validate_template(template: dict) -> dict:
    """Return a normalised deep copy of ``template``.

    Raises ``ValueError`` naming the field when the template is invalid.
    Missing ``buses`` and ``clips`` become empty lists; a track without a
    ``bus`` gets ``None``. The input is not mutated.
    """
    if not isinstance(template, dict):
        msg = f"template must be a mapping, got {type(template)!r}"
        raise ValueError(msg)  # noqa: TRY004 - the contract is plain ValueError

    version = template.get("version")
    if version != 1:
        msg = f"template version must be 1, got {version!r}"
        raise ValueError(msg)

    name = _non_empty_string(template.get("name"), "template name")

    buses: list[dict] = []
    seen_buses: set[str] = set()
    for bus in template.get("buses", []):
        bus_name = _non_empty_string(
            bus.get("name") if isinstance(bus, dict) else None, "bus name"
        )
        if bus_name in seen_buses:
            msg = f"duplicate bus name {bus_name!r}"
            raise ValueError(msg)
        seen_buses.add(bus_name)
        buses.append({"name": bus_name})

    tracks: list[dict] = []
    seen_tracks: set[str] = set()
    for track in template.get("tracks", []):
        track_name = _non_empty_string(
            track.get("name") if isinstance(track, dict) else None, "track name"
        )
        if track_name in seen_tracks:
            msg = f"duplicate track name {track_name!r}"
            raise ValueError(msg)
        seen_tracks.add(track_name)

        kind = track.get("kind")
        if kind not in _KINDS:
            msg = (
                f"track {track_name!r} kind must be speech or music, got {kind!r}"
            )
            raise ValueError(msg)

        bus = track.get("bus")
        if bus is not None and bus not in seen_buses:
            msg = f"track {track_name!r} bus {bus!r} is not a listed bus"
            raise ValueError(msg)

        tracks.append({"name": track_name, "kind": kind, "bus": bus})

    clips: list[dict] = []
    for clip in template.get("clips", []):
        track = clip.get("track")
        if track not in seen_tracks:
            msg = f"clip track {track!r} is not a listed track"
            raise ValueError(msg)

        media = _non_empty_string(clip.get("media"), "clip media")

        length = clip.get("length")
        if (
            not isinstance(length, (int, float))
            or isinstance(length, bool)
            or length <= 0
        ):
            msg = f"clip length must be positive, got {length!r}"
            raise ValueError(msg)

        anchor = clip.get("anchor")
        if not isinstance(anchor, dict):
            msg = "clip anchor must be an object"
            raise ValueError(msg)  # noqa: TRY004 - the contract is plain ValueError
        anchor = validate_anchor(anchor)

        clips.append(
            {"track": track, "media": media, "length": float(length), "anchor": anchor}
        )

    return {
        "version": 1,
        "name": name,
        "tracks": tracks,
        "buses": buses,
        "clips": clips,
    }
