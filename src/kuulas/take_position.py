"""Take position: where a take lands on the timeline.

``position_fields`` builds the position dict stored with a take,
``read_position`` reads it back from a parsed ``.take.json`` dict, and
``merge_position`` adds the fields to a metadata dict without mutating it.
Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations


def position_fields(
    start_frame: int, track_id: str | None
) -> dict[str, int | str | None]:
    """Return ``{"timeline_start", "track_id"}`` for a take.

    A negative start clamps to 0; a non-int start raises ``ValueError``;
    an empty-string track id becomes ``None``.
    """
    if not isinstance(start_frame, int):
        msg = f"start_frame must be an int, got {start_frame!r}"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError, not TypeError
    if track_id == "":
        track_id = None
    return {"timeline_start": max(0, start_frame), "track_id": track_id}


def read_position(meta: dict) -> dict[str, int | str | None] | None:
    """Read ``{"start", "track_id"}`` from a parsed ``.take.json`` dict.

    Returns None when the fields are missing, of the wrong type, or when
    ``timeline_start`` is negative. Unknown extra keys are tolerated and this
    never raises.
    """
    if not isinstance(meta, dict):
        return None
    start = meta.get("timeline_start")
    track_id = meta.get("track_id")
    if isinstance(start, bool) or not isinstance(start, int):
        return None
    if start < 0:
        return None
    if track_id is not None and not isinstance(track_id, str):
        return None
    return {"start": start, "track_id": None if track_id == "" else track_id}


def merge_position(
    meta: dict, start_frame: int, track_id: str | None
) -> dict[str, int | str | None]:
    """Return a new dict with the position fields added; ``meta`` is not mutated."""
    fields = position_fields(start_frame, track_id)
    return {**meta, **fields}
