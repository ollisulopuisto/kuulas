"""Edit scope and grouping rules (WP19a).

Determines what an edit touches:
- A time-shifting edit keeps the sync group together:
  - A range edit expands to every track in the sync group
    (or all tracks if outside any group).
  - A clip edit expands to each clip's partners (clips of the same sync group on
    other tracks playing the same stretch of recording).
- Any other edit touches exactly what was selected.
- A clip declared free from sync (``Clip.free``) is no one's partner: moving it
  takes nobody along, and nobody's move takes it along.
"""

from __future__ import annotations

from collections.abc import Sequence
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


def expand_range(
    project: Project,
    material: Any,
    tracks: Sequence[str | Track] | set[str],
    start: int,
    end: int,
    group_editing: bool,
) -> list[str]:
    """For a time-shifting range edit, return the tracks to apply it to:
    every track of the group when ``group_editing`` is on, else just ``tracks``;
    tracks outside any group follow the old rule (all tracks).
    """
    track_ids = [t if isinstance(t, str) else t.id for t in tracks]
    if not group_editing:
        return list(track_ids)

    groups = _sync_groups(project, material)
    p = replace(project, sync_groups=groups) if project.sync_groups != groups else project

    # Identify sync groups associated with the selected tracks
    target_group_ids: set[str] = set()
    track_map = {t.id: t for t in p.tracks}

    for tid in track_ids:
        t = track_map.get(tid)
        if t is None:
            continue
        # Check clips in range first, or all clips on track if none in range
        in_range_clips = [c for c in t.clips if c.start < end and c.end > start]
        clips_to_check = in_range_clips if in_range_clips else list(t.clips)
        t_groups = {
            g.id for c in clips_to_check if (g := p.sync_group(c.media)) is not None
        }
        if not t_groups:
            # This track is outside any sync group -> follow old rule (all tracks)
            return [tr.id for tr in p.tracks]
        target_group_ids.update(t_groups)

    if not target_group_ids:
        return [tr.id for tr in p.tracks]

    # Expand to all project tracks that belong to any of target_group_ids
    out: list[str] = []
    for tr in p.tracks:
        tr_groups = {g.id for c in tr.clips if (g := p.sync_group(c.media)) is not None}
        if (tr_groups & target_group_ids) or (tr.id in track_ids):
            out.append(tr.id)

    return out


def expand_clips(
    project: Project,
    material: Any,
    clip_ids: Sequence[str] | set[str],
    group_editing: bool,
) -> list[str]:
    """For a time-shifting clip edit, return the clip ids plus their partners
    when ``group_editing`` is on, else just the selected clips.
    """
    initial_ids = list(clip_ids)
    if not group_editing:
        return initial_ids

    out = list(initial_ids)
    seen = set(out)
    for cid in initial_ids:
        for partner in partners(project, material, cid):
            if partner.id not in seen:
                seen.add(partner.id)
                out.append(partner.id)

    return out


#: The kinds of edit that shift time (WP19a). Everything else (gain, pan, mute,
#: fades, FX, delete leaving a gap, trim without ripple) uses its target exactly.
TIME_SHIFTING = frozenset({
    "cut", "close_gap", "ripple_delete", "insert", "move", "nudge", "ripple_trim",
    "cut_words",
})


def edit_target(project: Project, material: Any, kind: str, target: dict,
                group_editing: bool) -> dict:
    """The one answer to "what does this edit touch?".

    ``target`` is a range ``{"track_ids", "start", "end"}`` or a clip set
    ``{"clip_ids"}``; the answer has the same keys with ``track_ids`` or
    ``clip_ids`` widened when ``kind`` shifts time and ``group_editing`` is on,
    and is a copy of ``target`` otherwise. Other keys pass through.
    """
    out = dict(target)
    if kind not in TIME_SHIFTING or not group_editing:
        return out
    if target.get("clip_ids") is not None:
        out["clip_ids"] = expand_clips(project, material, target["clip_ids"], True)
    elif target.get("track_ids") is not None:
        out["track_ids"] = expand_range(
            project, material, list(target["track_ids"]), int(target["start"]),
            int(target["end"]), True)
    return out
