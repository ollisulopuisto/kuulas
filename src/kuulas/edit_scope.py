"""What an edit touches (WP83; WP19a before it).

Three separate ideas, never mixed:

- Sync is knowledge only. ``partners`` says which clips on other tracks play
  the same stretch of recording (Resync, Free, the drift list and badges use it).
  No edit ever moves, trims, deletes or mutes a clip because it is a sync partner.
- An explicit group (``Clip.group``, Group clips) is the only thing that makes
  clips move, trim, delete or mute together: ``expand_clips``.
- A range operation acts on a rectangle of time by tracks. ``range_tracks`` is the
  one place that turns the requested track set into the tracks to edit: nothing
  given means all tracks (the default, so one track is never edited by accident).
- A clip declared free from sync (``Clip.free``) is no one's partner.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from . import clock, history
from .model import Clip, Project, SyncGroup, Track


def _sync_groups(project: Project, material: Any) -> tuple[SyncGroup, ...]:
    """Extract sync groups from material root or project."""
    if material is None:
        return project.sync_groups
    if isinstance(material, dict):
        if "sync" in material:
            return history.sync_groups(material)
        return history.sync_groups({"sync": material})
    if isinstance(material, (tuple, list)):
        return tuple(material)
    return project.sync_groups


def _recorded_range(p: Project, clip: Clip) -> tuple[int, int] | None:
    """Return ``(recorded_start, recorded_end)`` on the group's clock in project frames,
    or None if the clip's media is not in any sync group."""
    member = p.sync_member(clip.media)
    if member is None:
        return None
    _group, origin_flicks = member
    origin_frames = clock.flicks_to_frames(origin_flicks, p.rate)
    start = clip.offset + origin_frames
    return start, start + clip.length


def partners(project: Project, material: Any, clip_id: str) -> list[Clip]:
    """Return clips of the same sync group on other tracks that play the same stretch
    of recording.

    Partners are found by recording time, not by timeline position.
    """
    groups = _sync_groups(project, material)
    p = replace(project, sync_groups=groups) if project.sync_groups != groups else project

    try:
        clip, _track = p.clip_and_track(clip_id)
    except (KeyError, ValueError):
        return []

    group = p.sync_group(clip.media)
    if group is None or clip.free:
        return []

    c_rec = _recorded_range(p, clip)
    if c_rec is None:
        return []
    c_start, c_end = c_rec

    res: list[Clip] = []
    for other_track in p.tracks:
        for other_clip in other_track.clips:
            # Never itself; a clip dragged onto its partner's track is still a partner.
            if (other_clip.id == clip.id or other_clip.free
                    or p.sync_group(other_clip.media) != group):
                continue
            o_rec = _recorded_range(p, other_clip)
            if o_rec is None:
                continue
            o_start, o_end = o_rec
            # Overlap in recording time
            if max(c_start, o_start) < min(c_end, o_end):
                res.append(other_clip)

    return sorted(res, key=lambda c: (c.start, c.id))


def range_tracks(project: Project,
                 track_ids: Iterable[str | Track] | None = None) -> list[str]:
    """The tracks a range operation (cut, copy, lift-cut, close gap, delete, mute)
    acts on, in project order. ``None`` (not given) means all tracks; so does an
    empty list, so a range operation can never silently become a no-op or an edit
    of one track. Unknown ids are an error (``KeyError``)."""
    order = [t.id for t in project.tracks]
    if track_ids is None:
        return order
    wanted = {t if isinstance(t, str) else t.id for t in track_ids}
    if not wanted:
        return order
    unknown = wanted - set(order)
    if unknown:
        raise KeyError(sorted(unknown)[0])
    return [tid for tid in order if tid in wanted]


def expand_clips(project: Project, clip_ids: Iterable[str]) -> list[str]:
    """The clip ids plus every member of an explicit group any of them belongs to.
    Sync partners are not included (WP83): sync never moves anything."""
    initial = list(dict.fromkeys(clip_ids))
    groups = {c.group for t in project.tracks for c in t.clips
              if c.id in set(initial) and c.group is not None}
    if not groups:
        return initial
    out = list(initial)
    seen = set(out)
    for t in project.tracks:
        for c in t.clips:
            if c.group in groups and c.id not in seen:
                seen.add(c.id)
                out.append(c.id)
    return out
