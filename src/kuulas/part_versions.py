"""Derived versions of one track range (WP80); no extra project data is stored."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, replace

from .model import Clip, Project
from .ops import range_clips as snapshot


def gate_snapshot(project: Project, track_id: str, start: int, end: int):
    return tuple((max(a, start) - start, min(b, end) - start)
                 for a, b in project.track(track_id).gate if a < end and b > start)


def signature(clips: tuple[Clip, ...], gate=()) -> str:
    """Ignore cosmetic identity and merge source-contiguous artificial seams."""
    parts = []
    for clip in clips:
        part = clip.to_dict()
        for key in ("id", "name", "group", "home", "free"):
            part.pop(key, None)
        if parts:
            previous = parts[-1]
            ignored = {"start", "offset", "length", "fade_in", "fade_out",
                       "xfade_in", "xfade_out"}
            same = {k: v for k, v in part.items() if k not in ignored} == {
                k: v for k, v in previous.items() if k not in ignored}
            if (same and previous["start"] + previous["length"] == part["start"]
                    and previous["offset"] + previous["length"] == part["offset"]
                    and not previous["fade_out"] and not part["fade_in"]
                    and not previous["xfade_out"] and not part["xfade_in"]):
                previous["length"] += part["length"]
                previous["fade_out"] = part["fade_out"]
                previous["xfade_out"] = part["xfade_out"]
                continue
        parts.append(part)
    return json.dumps([parts, gate], sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class PartVersion:
    clips: tuple[Clip, ...]
    first_node: str
    last_node: str
    current: bool = False


def distinct_versions(states: Iterable[tuple[str, Project]], track_id: str,
                      start: int, end: int, *, current: str | None = None
                      ) -> list[PartVersion]:
    """Read states oldest first, return distinct contents newest first.

    A missing track predates its creation and is not an empty version. A track
    that exists without clips *is* a recoverable silence version.
    """
    found: dict[str, PartVersion] = {}
    current_key = None
    for node, project in states:
        if not any(t.id == track_id for t in project.tracks):
            continue
        clips = snapshot(project, track_id, start, end)
        key = signature(clips, gate_snapshot(project, track_id, start, end))
        earlier = found.pop(key, None)
        found[key] = PartVersion(clips, earlier.first_node if earlier else node, node)
        if node == current:
            current_key = key
    return [replace(version, current=key == current_key)
            for key, version in reversed(found.items())]
