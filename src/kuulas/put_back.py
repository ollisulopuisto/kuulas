"""Putting removed material back: where it goes (T64).

A removed stretch of a recording is put back at the place it was cut from, and that
place is measured on the recording clock, not by remembered timeline times: the first
ripple after a cut makes any stored position stale. ``locate`` reads the clips of the
recording's sync group (the hit's own recording and its partners; a recording with no
group is a group of one), converts them to the recording clock and says which of these
the cut looks like:

``FILL``       a partner still plays the stretch; it goes on this recording's track at the
               matching time, nothing moves.
``HOLE``       the clips on either side are on one track and the timeline gap between
               them is as long as the source gap: the gap is filled in place.
``SEAM``       the cut was closed up: the neighbours on every track that has both meet at
               one frame; material goes in there as a ripple insert.
``EDGE``       group material exists on one side only; the insert is at that side's edge.
``AMBIGUOUS``  the neighbours were moved apart, sit on different tracks, or disagree
               between tracks. No guess: ``candidates`` lists the frames to choose from.
``NONE``       no clip of the group is on the timeline.

Frames are project frames. Positions are exact: ``ripple_delete`` keeps ``L.end ==
N.start`` to the frame, so there is no tolerance to tune.
"""

from __future__ import annotations

from dataclasses import dataclass

from .clock import flicks_to_frames
from .model import Clip, Project
from .ops import _recorded

FILL, HOLE, SEAM, EDGE = "fill", "hole", "seam", "edge"
AMBIGUOUS, NONE = "ambiguous", "none"


@dataclass(frozen=True)
class Site:
    """Where a removed stretch goes. ``frame``: the timeline frame (None for AMBIGUOUS
    and NONE); ``track``: the track of the hit's own recording that holds it, for FILL
    and HOLE; ``candidates``: the frames an AMBIGUOUS cut could be put back at;
    ``why``: a short reason for AMBIGUOUS."""

    kind: str
    frame: int | None = None
    track: str | None = None
    candidates: tuple[int, ...] = ()
    why: str = ""


@dataclass(frozen=True)
class _Placed:
    """A clip of the group with its stretch on the recording clock."""

    track: str
    clip: Clip
    start: int  # recording clock, project frames
    end: int

    @property
    def tl_end(self) -> int:
        return self.clip.end


def _group(project: Project, media: str) -> set[str]:
    found = project.sync_member(media)
    if found is None:
        return {media}
    return {found[0].main, *(m for m, _ in found[0].members), media}


def _origin(project: Project, media: str) -> int:
    found = project.sync_member(media)
    return 0 if found is None else flicks_to_frames(found[1], project.rate)


def _placed(project: Project, group: set[str]) -> list[_Placed]:
    out = []
    for track in project.tracks:
        for clip in track.clips:
            if clip.media in group and not clip.free:
                rec = _recorded(project, clip)
                out.append(_Placed(track.id, clip, rec, rec + clip.length))
    return out


def _fill(media: str, placed: list[_Placed], rx: int, ry: int) -> Site | None:
    """A partner that plays all of ``[rx, ry)``: the stretch goes on this recording's
    track at the same moment. None when no partner does."""
    covering = next((p for p in placed
                     if p.clip.media != media and p.start <= rx and p.end >= ry), None)
    if covering is None:
        return None
    own = [p for p in placed if p.clip.media == media]
    if not own:
        return None
    # This recording's track: the one holding its nearest piece before, else after.
    before = [p for p in own if p.end <= rx]
    pick = max(before, key=lambda p: p.end) if before else min(own, key=lambda p: p.start)
    frame = covering.clip.start + (rx - covering.start)
    length = ry - rx
    for other in placed:
        if (other.track == pick.track and other.clip.start < frame + length
                and frame < other.clip.end):
            return Site(AMBIGUOUS, candidates=(frame,), why="conflict")
    return Site(FILL, frame, pick.track)


def _hole(project: Project, media: str, x: int, y: int) -> Site | None:
    """The pieces of this recording on either side are on one track with the same gap
    on the timeline as in the source: the stretch fills the gap where it was."""
    for track in project.tracks:
        own = [c for c in track.clips if c.media == media and not c.free]
        before = [c for c in own if c.offset + c.length <= x]
        after = [c for c in own if c.offset >= y]
        if not before or not after:
            continue
        left = max(before, key=lambda c: c.offset + c.length)
        right = min(after, key=lambda c: c.offset)
        source_gap = right.offset - (left.offset + left.length)
        if source_gap > 0 and right.start - left.end == source_gap:
            return Site(HOLE, left.end + (x - (left.offset + left.length)), track.id)
    return None


def locate(project: Project, media: str, start_flicks: int, end_flicks: int) -> Site:
    """Where ``[start_flicks, end_flicks)`` of recording ``media`` goes back (see the
    module text). The span is on the recording's own clock, as the words are."""
    x = flicks_to_frames(start_flicks, project.rate)
    y = max(x + 1, flicks_to_frames(end_flicks, project.rate))
    origin = _origin(project, media)
    rx, ry = x + origin, y + origin
    placed = _placed(project, _group(project, media))
    if not placed:
        return Site(NONE)
    filled = _fill(media, placed, rx, ry)
    if filled is not None:
        return filled
    hole = _hole(project, media, x, y)
    if hole is not None:
        return hole
    return _closed_up(project, placed, rx, ry)


def _closed_up(project: Project, placed: list[_Placed], rx: int, ry: int) -> Site:
    """The cut was closed up (or the material ends here): read the nearest group piece
    either side of the stretch, per track."""
    seams: set[int] = set()
    disagree: set[int] = set()
    lefts: list[_Placed] = []
    rights: list[_Placed] = []
    for track in project.tracks:
        mine = [p for p in placed if p.track == track.id]
        before = [p for p in mine if p.end <= rx]
        after = [p for p in mine if p.start >= ry]
        left = max(before, key=lambda p: p.end) if before else None
        right = min(after, key=lambda p: p.start) if after else None
        if left and right:
            if left.tl_end == right.clip.start:
                seams.add(left.tl_end)
            else:
                disagree.update((left.tl_end, right.clip.start))
        elif left:
            lefts.append(left)
        elif right:
            rights.append(right)
    if seams or disagree:
        if len(seams) == 1 and not disagree:
            return Site(SEAM, next(iter(seams)))
        return Site(AMBIGUOUS, candidates=tuple(sorted(seams | disagree)), why="seams")
    if lefts and not rights:
        edges = {p.tl_end for p in lefts}
    elif rights and not lefts:
        edges = {p.clip.start for p in rights}
    else:  # material on both sides, but never on one track
        edges = {p.tl_end for p in lefts} | {p.clip.start for p in rights}
        return Site(AMBIGUOUS, candidates=tuple(sorted(edges)), why="tracks")
    if len(edges) == 1:
        return Site(EDGE, next(iter(edges)))
    return Site(AMBIGUOUS, candidates=tuple(sorted(edges)), why="edges")
