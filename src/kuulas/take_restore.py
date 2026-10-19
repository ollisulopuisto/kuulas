"""Planning placement and targeting when restoring a recorded take.

Pure Python logic for determining destination track, start frame, and
replacement behavior.
"""

from __future__ import annotations

from typing import Any

VALID_MODES = {"new_track_original", "playhead", "original", "clipboard"}


def restore_plan(
    mode: str = "new_track_original",
    original: dict[str, Any] | None = None,
    playhead: int = 0,
    duration: int = 0,  # noqa: ARG001 - reserved for future duration bounds
    current_track_id: str | None = None,
) -> dict[str, Any]:
    """Calculate the restore plan for a recorded take based on the chosen mode."""
    if mode not in VALID_MODES:
        msg = f"Unknown mode: {mode!r}; valid modes are {sorted(VALID_MODES)}"
        raise ValueError(msg)

    if mode == "new_track_original":
        target = "new_track"
        track_id = None
        raw_start = (
            original.get("start")
            if original and original.get("start") is not None
            else playhead
        )
        start: int | None = max(0, int(raw_start))
        replaces = False

    elif mode == "playhead":
        target = "track" if current_track_id is not None else "new_track"
        track_id = current_track_id
        start = max(0, int(playhead))
        replaces = True

    elif mode == "original":
        orig_track = original.get("track_id") if original else None
        target = "track" if orig_track is not None else "new_track"
        track_id = orig_track
        raw_start = (
            original.get("start")
            if original and original.get("start") is not None
            else playhead
        )
        start = max(0, int(raw_start))
        replaces = True

    elif mode == "clipboard":
        target = "clipboard"
        track_id = None
        start = None
        replaces = False

    return {
        "target": target,
        "track_id": track_id,
        "start": start,
        "replaces": replaces,
    }
