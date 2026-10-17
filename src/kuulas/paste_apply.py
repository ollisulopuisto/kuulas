"""Turning a paste plan into a new project (WP46 wiring).

``paste_plan.plan_paste`` says what a paste would do; this applies it with the
existing ops, as one pure ``Project -> Project`` step the session commits as a
single undo step. An insert ripples the later material on the target tracks
(clips, automation and the Auto-Silence gate move together, as in a ripple
delete, so nothing drifts out of step with its audio) and an overwrite
removes the covered stretches without moving anything; both then add the
pasted clips.
"""

from __future__ import annotations

from dataclasses import replace

from . import curves, ops
from . import gate as gatem
from .clipboard import Entry
from .model import Project, Track
from .paste_plan import PastePlan


def _split_at(p: Project, track_id: str, frame: int) -> Project:
    """Split the clips of one track that ``frame`` lies inside (adjacent
    audio, so no crossfade); nothing to split is fine."""
    inside = [c.id for c in p.track(track_id).clips if c.start < frame < c.end]
    return ops.split_clips(p, frame, inside) if inside else p


def _open_gap(p: Project, track_id: str, at: int, length: int) -> Project:
    """Make ``length`` empty frames at ``at`` on one track: the inverse of the
    ripple delete, for the clips, the automation and the gate."""
    p = _split_at(p, track_id, at)
    later = [c.id for c in p.track(track_id).clips if c.start >= at]
    if later:
        p = ops.shift_clips(p, later, length)
    track: Track = p.track(track_id)
    automation = track.automation
    if automation:
        # Hold the level across the gap, so the pasted audio is not bent by
        # a ramp that was meant for the material on either side.
        level = curves.value_at(automation, at)
        moved = [(f + length, db) for f, db in automation if f >= at]
        before = [pt for pt in automation if pt[0] < at]
        automation = (*before, (at, level), (at + length, level), *moved)
    gate = []
    for a, b in track.gate:
        if b <= at:
            gate.append((a, b))
        elif a >= at:
            gate.append((a + length, b + length))
        else:  # the gate straddles the point: the gap itself stays open
            gate.extend([(a, at), (at + length, b + length)])
    track = replace(track, automation=automation, gate=gatem.normalise(gate))
    return replace(p, tracks=tuple(track if t.id == track_id else t for t in p.tracks))


def _clear(p: Project, track_id: str, start: int, end: int) -> Project:
    """Remove ``[start, end)`` from one track and leave the gap (no ripple)."""
    p = _split_at(_split_at(p, track_id, start), track_id, end)
    inside = [c.id for c in p.track(track_id).clips if c.start >= start and c.end <= end]
    return ops.delete_clips(p, inside)


def apply_paste(project: Project, entry: Entry, plan: PastePlan, at: int,
                rippled: set[str], mode: str) -> Project:
    """``project`` with ``plan`` done at frame ``at``. ``rippled`` are the tracks an insert
    ripples (the targets, and their sync group when group editing is on). Refs
    whose media the project lacks are not placed.
    """
    p = project
    if mode == "insert":
        for track in project.tracks:  # project order, so the result is stable
            if track.id in rippled:
                p = _open_gap(p, track.id, at, plan.shift)
    else:
        for track_id, start, end in plan.removed:
            p = _clear(p, track_id, start, end)
    media = {}
    for item in project.media:
        media.setdefault(item.sha256, item.id)
    present = [ref for ref in entry.refs if ref.media_sha256 in media]
    for ref, placed in zip(present, plan.placements, strict=True):
        track_id, sha, start, offset, length, gain, pan, fade_in, fade_out, muted = placed
        clip_id = ops.new_id("c")
        p = ops.add_clip(p, track_id, media[sha], start, offset, length, clip_id)
        p = ops.set_clip(p, clip_id, gain_db=gain, pan=pan, fade_in=fade_in,
                         fade_out=fade_out, muted=muted)
        if ref.envelope:
            p = ops.set_clip_envelope(p, clip_id, ref.envelope)
    return p

