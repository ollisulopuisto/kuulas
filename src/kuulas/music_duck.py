"""The music ducking state recorded for the automixer export."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Project, Track


def signature(track: Track) -> str:
    """Identify the track's editable duck curve and the clips it describes."""
    rows = {
        "automation": [list(point) for point in track.automation],
        "clips": [clip.to_dict() for clip in track.clips],
    }
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def record(p: Project, at: str | None) -> dict | None:
    """The command-time record, matching block level's apply-time record."""
    tracks = {track.id: signature(track) for track in p.tracks
              if track.kind == "music" and track.duck is not False and track.automation}
    if not tracks:
        return None
    return {"applied": True, "tracks": tracks, **({"set_at": at} if at else {})}


def current(p: Project) -> dict | None:
    """Return the record only while the music curves and their clips still match."""
    entry = (p.mix_done or {}).get("music_duck")
    if not isinstance(entry, dict) or entry.get("applied") is not True:
        return None
    tracks = entry.get("tracks")
    if not isinstance(tracks, dict):
        return None
    now = {track.id: signature(track) for track in p.tracks
           if track.kind == "music" and track.duck is not False and track.automation}
    return entry if now == tracks else None


def with_record(p: Project, at: str | None) -> Project:
    done = dict(p.mix_done or {})
    entry = record(p, at)
    if entry is None:
        done.pop("music_duck", None)
    else:
        done["music_duck"] = entry
    return replace(p, mix_done=done)
