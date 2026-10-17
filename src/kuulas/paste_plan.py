"""Where a paste would land (WP46, second part).

Takes a clipboard ``Entry`` (WP46, first part, ``clipboard``) and returns
what a paste would do, without changing anything: the new clips, the
frames later material moves, and, for an overwrite, the stretches it
would replace. The session wiring turns a plan into edits.

This is the logic only: no audio, no file I/O, no session wiring. The
entry is expected well formed, as ``clipboard``'s makers leave it: a span
that covers the refs, and dense ``track_slot`` numbers in the source
project's track order.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .clipboard import Entry
from .messages import KuulasError
from .model import Project
from .ops import EditError

# One clip a paste would add: where it lands and the window it plays.
Placement = tuple[str, str, int, int, int, float, float, int, int, bool]

_INSERT = "insert"
_OVERWRITE = "overwrite"


@dataclass(frozen=True)
class PastePlan:
    """What a paste of one entry would do.

    ``placements`` holds the new clips as ``(track_id, media_sha256,
    start, offset, length, gain_db, pan, fade_in, fade_out, muted)`` in
    the entry's own ref order. The placement carries no envelope: the
    entry's refs still hold theirs, so the wiring can read them there.
    ``shift`` is the frames later material moves right by (0 for an
    overwrite). ``removed`` holds the ``(track_id, start, end)``
    stretches an overwrite replaces, in project track order, one per
    target track that has material under the paste. ``missing`` holds
    the media digests the project does not have, sorted and unique;
    their clips are not placed.
    """

    placements: tuple[Placement, ...] = ()
    shift: int = 0
    removed: tuple[tuple[str, int, int], ...] = ()
    missing: tuple[str, ...] = ()


def _targets(project: Project, entry: Entry,
             target_tracks: Mapping[int, str] | None) -> dict[int, str]:
    """The track id each used ``track_slot`` of the entry lands on.

    ``target_tracks`` maps slots to track ids; a slot the entry uses but
    the mapping lacks raises, and so does a track the project does not
    have. Slots the entry does not use are neither validated nor pasted.

    ``None`` means the source's own tracks where they exist, else the
    first tracks in order. ``clipboard`` numbers the source tracks in
    the source project's order, so slot ``i`` is that project's ``i``-th
    track: pasting into the source project lands on the same tracks, and
    pasting into any other degrades to that project's first tracks —
    which, for dense slots, is what "the first tracks in order" is.
    """
    used = sorted({ref.track_slot for ref in entry.refs})
    if target_tracks is None:
        for slot in used:
            if not 0 <= slot < len(project.tracks):
                raise KuulasError("error.paste.missing_slot", slot=slot)
        return {slot: project.tracks[slot].id for slot in used}
    resolved: dict[int, str] = {}
    for slot in used:
        if slot not in target_tracks:
            raise KuulasError("error.paste.missing_slot", slot=slot)
        track_id = target_tracks[slot]
        try:
            project.track(track_id)
        except KeyError:
            raise EditError("error.edit.no_track",
                            track_id=track_id) from None
        resolved[slot] = track_id
    return resolved


def plan_paste(project: Project, entry: Entry, at: int,
               mode: str = _INSERT,
               target_tracks: Mapping[int, str] | None = None) -> PastePlan:
    """What pasting ``entry`` at frame ``at`` in ``mode`` would do.

    ``mode`` is ``"insert"`` (ripple: later material moves right by the
    entry's length on the target tracks; nothing is overwritten) or
    ``"overwrite"`` (the stretch is replaced in place; the clips under it
    are cut back). The entry lands so that its ``span[0]``'s material
    sits at ``at``, and occupies ``[at, at + span length)`` however many
    of its media the project lacks. A media found by its SHA-256 that
    the project does not have is not an error: it is reported in
    ``PastePlan.missing`` and its clips are left out.
    """
    if mode not in (_INSERT, _OVERWRITE):
        raise KuulasError("error.paste.unknown_mode", mode=mode)
    targets = _targets(project, entry, target_tracks)
    digests = {item.sha256 for item in project.media}
    placements = tuple(
        (targets[ref.track_slot], ref.media_sha256, at + ref.rel_start,
         ref.offset, ref.length, ref.gain_db, ref.pan, ref.fade_in,
         ref.fade_out, ref.muted)
        for ref in entry.refs if ref.media_sha256 in digests)
    missing = tuple(sorted({ref.media_sha256 for ref in entry.refs
                            if ref.media_sha256 not in digests}))
    length = entry.span[1] - entry.span[0]
    if mode == _INSERT:
        return PastePlan(placements, length, (), missing)
    end = at + length
    landed = set(targets.values())
    # A clip is under the paste when it overlaps it by at least one
    # frame; one that only touches an edge is not.
    removed = tuple(
        (track.id, at, end)
        for track in project.tracks
        if track.id in landed
        and any(not (clip.end <= at or end <= clip.start)
                for clip in track.clips))
    return PastePlan(placements, 0, removed, missing)
