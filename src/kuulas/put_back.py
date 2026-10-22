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

from . import source_map
from .clipboard import ClipRef, Entry, entry_from_refs
from .clock import FLICKS, flicks_to_frames, frames_to_flicks
from .model import Clip, Project
from .ops import EditError, _recorded
from .paste_apply import apply_paste
from .paste_plan import plan_paste
from .source_map import _resolve_recording

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


@dataclass(frozen=True)
class Plan:
    """What putting a stretch back would do, in one value for the preview and the edit.

    ``mode``: ``"insert"`` (a ripple insert at ``at`` on the tracks in ``scope``),
    ``"place"`` (into empty space, nothing moves) or ``""`` when ``blocked``.
    ``length``: the frames of material; ``shift``: how far later everything after ``at``
    moves (0 for ``place``). ``outcomes``: ``(track id, outcome)`` for every track the
    edit touches or leaves alone on purpose: ``restored``, ``still_in_edit`` (a partner
    still plays it), ``silence`` (that recording does not reach the stretch),
    ``cut_differently`` (the track was cut elsewhere: it only gets the gap), ``split`` and
    ``shifted`` (a track that is not the recording's: a clip across ``at`` is split and
    opened, or later clips move). ``blocked``: ``ambiguous``, ``none``, ``no_track`` or
    ``nothing`` when it cannot be done; the site's ``candidates`` are the choices."""

    site: Site
    at: int | None
    mode: str
    length: int
    shift: int
    scope: tuple[str, ...]
    outcomes: tuple[tuple[str, str], ...]
    entry: Entry | None
    blocked: str = ""


def _blocked(site: Site, length: int, scope: tuple[str, ...], reason: str) -> Plan:
    return Plan(site, None, "", length, 0, scope, (), None, blocked=reason)


def _own_clip(project: Project, media: str, rx: int) -> tuple[str, Clip] | None:
    """The piece of ``media`` nearest the stretch on the recording clock: the track the
    stretch goes on when the cut itself cannot say."""
    best: tuple[int, str, Clip] | None = None
    for track in project.tracks:
        for c in track.clips:
            if c.media != media or c.free:
                continue
            rec = _recorded(project, c)
            distance = 0 if rec <= rx < rec + c.length else min(
                abs(rec - rx), abs(rec + c.length - rx))
            if best is None or distance < best[0]:
                best = (distance, track.id, c)
    return None if best is None else (best[1], best[2])


def _ref(project: Project, media: str, rx: int, ry: int, slot: int,
         neighbour: Clip) -> ClipRef | None:
    """A reference to ``[rx, ry)`` (recording clock) of ``media``, levelled like the
    piece beside it; None when that recording does not reach the stretch."""
    item = project.media_item(media)
    offset = rx - _origin(project, media)
    if offset < 0 or offset + (ry - rx) > item.frames:
        return None
    return ClipRef(item.sha256, offset, ry - rx, gain_db=neighbour.gain_db,
                   pan=neighbour.pan, track_slot=slot, media_name=item.name)


def _other_track(track, at: int) -> str:
    """What an insert does to a track that holds none of the group's recordings."""
    if any(c.start < at < c.end for c in track.clips):
        return "split"
    return "shifted" if any(c.start >= at for c in track.clips) else "empty"


def plan(project: Project, media: str, start_flicks: int, end_flicks: int, *,
         scope: list[str] | tuple[str, ...] | None = None, at: int | None = None) -> Plan:
    """The plan for putting ``[start_flicks, end_flicks)`` of ``media`` back.

    ``scope``: the tracks that open a gap (default every track: the same rule as X).
    ``at``: put it at this frame instead (the playhead): the only way out of an AMBIGUOUS
    or NONE cut, and what Alt+Enter does. Nothing is guessed without it."""
    x = flicks_to_frames(start_flicks, project.rate)
    y = max(x + 1, flicks_to_frames(end_flicks, project.rate))
    length = y - x
    rx = x + _origin(project, media)
    ry = rx + length
    tracks = tuple(scope) if scope is not None else tuple(t.id for t in project.tracks)
    site = locate(project, media, start_flicks, end_flicks)
    if at is None and site.kind in (AMBIGUOUS, NONE):
        return _blocked(site, length, tracks, site.kind)
    group = _group(project, media)
    slots = {t.id: i for i, t in enumerate(project.tracks)}
    if at is None and site.kind in (FILL, HOLE):
        return _place(project, media, site, x, length, slots, group)
    frame = at if at is not None else site.frame
    refs: list[ClipRef] = []
    outcomes: list[tuple[str, str]] = []
    own = _own_clip(project, media, rx) if site.kind in (AMBIGUOUS, NONE) or at else None
    for track in project.tracks:
        if track.id not in tracks:
            continue
        mine = [c for c in track.clips if c.media in group and not c.free]
        if not mine:
            outcomes.append((track.id, _other_track(track, frame)))
            continue
        if own is not None:
            left = own[1] if track.id == own[0] else None
            right = None
        else:
            left = next((c for c in mine if c.end == frame), None)
            right = next((c for c in mine if c.start == frame), None)
        neighbour = left or right
        if neighbour is None:
            outcomes.append((track.id, "cut_differently"))
            continue
        ref = _ref(project, neighbour.media, rx, ry, slots[track.id], neighbour)
        if ref is None:
            outcomes.append((track.id, "silence"))
        else:
            refs.append(ref)
            outcomes.append((track.id, "restored"))
    if not refs:
        return _blocked(site, length, tracks,
                        "no_track" if own is None and at else "nothing")
    entry = entry_from_refs(refs, name="put back", span=(0, length))
    return Plan(site, frame, "insert", length, length, tracks, tuple(outcomes), entry)


def _place(project: Project, media: str, site: Site, x: int, length: int,
           slots: dict[str, int], group: set[str]) -> Plan:
    """FILL and HOLE: into empty space on the recording's own track, nothing moves."""
    own = next(c for c in project.track(site.track).clips if c.media == media)
    ref = _ref(project, media, x + _origin(project, media), x + _origin(project, media)
               + length, slots[site.track], own)
    outcomes = [(site.track, "restored")]
    if site.kind == FILL:
        outcomes += [(t.id, "still_in_edit") for t in project.tracks
                     if t.id != site.track
                     and any(c.media in group and not c.free for c in t.clips)]
    if ref is None:
        return _blocked(site, length, (), "nothing")
    entry = entry_from_refs([ref], name="put back", span=(0, length))
    return Plan(site, site.frame, "place", length, 0, (), tuple(outcomes), entry)


def apply(project: Project, plan: Plan) -> Project:
    """``project`` with ``plan`` done, as one pure step (the session commits it once).
    Only clips are added; no recording is touched. A blocked plan raises."""
    if plan.blocked or plan.entry is None or plan.at is None:
        raise EditError("error.put_back.blocked", reason=plan.blocked or "nothing")
    mode = "insert" if plan.mode == "insert" else "overwrite"
    paste = plan_paste(project, plan.entry, plan.at, mode)
    return apply_paste(project, plan.entry, paste, plan.at, set(plan.scope), mode)


#: A pause longer than this ends a sentence even without a full stop.
SENTENCE_GAP = FLICKS
#: A remainder of the removed block shorter than this is a sliver: the whole block
#: returns.
SLIVER = FLICKS
#: A removed block longer than this (a recording placed nowhere) never returns
#: whole.
MAX_BLOCK = 120 * FLICKS
#: A sentence that is more than this share of its block takes the whole block.
WHOLE_SHARE = 2 / 3
_STOPS = ".!?\u2026"


def _inside(ranges: list[tuple[int, int]], point: int) -> bool:
    return any(a <= point < b for a, b in ranges)


def choose_range(project: Project, media: str, words: list[dict], first: int,
                 last: int) -> tuple[int, int]:
    """The default stretch to put back for a hit on ``words[first..last]`` of ``media``:
    its sentence (to a full stop, a pause over a second, or a change of speaker), padded
    to the middle of the pauses like a cut, and kept inside the removed block around it,
    so nothing the edit still plays comes back twice. A sliver left over, or a sentence
    that is most of the block, takes the whole block (never one over two minutes: a
    recording placed nowhere). ``(start, end)`` in flicks from the recording's start."""
    media_by = {m.id: m for m in project.media}
    item = media_by[media]
    resolved = _resolve_recording(item, media_by)
    sha, origin = resolved if resolved is not None else (item.sha256, 0)
    used, _cut, _unused = source_map.coverage(project, sha)

    def heard(i: int) -> bool:
        return _inside(used, origin + (words[i]["s"] + words[i]["e"]) // 2)

    def joins(a: int, b: int) -> bool:
        """Do neighbouring words ``a`` then ``b`` belong to one sentence?"""
        before, after = words[a], words[b]
        return (not heard(b) and after["s"] - before["e"] <= SENTENCE_GAP
                and before["w"][-1:] not in _STOPS
                and before.get("spk", "") == after.get("spk", ""))

    i, j = first, last
    while i > 0 and joins(i - 1, i):
        i -= 1
    while j < len(words) - 1 and joins(j, j + 1):
        j += 1
    start = words[i]["s"]
    if i > 0:
        start = (words[i - 1]["e"] + start) // 2
    end = words[j]["e"]
    if j < len(words) - 1:
        end = (end + words[j + 1]["s"]) // 2
    a, b = origin + words[first]["s"], origin + words[last]["e"]
    lo = max((e for _s, e in used if e <= a), default=origin) - origin
    hi = min((s for s, _e in used if s >= b),
             default=origin + frames_to_flicks(item.frames, project.rate)) - origin
    start, end = max(start, lo), min(end, hi)
    block = hi - lo
    slivers = 0 < start - lo < SLIVER or 0 < hi - end < SLIVER
    if block <= MAX_BLOCK and (slivers or end - start > WHOLE_SHARE * block):
        return lo, hi
    return start, end
