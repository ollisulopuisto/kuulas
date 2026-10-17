"""Edits: pure functions ``Project -> Project``.

Each one is a single undo step. ``apply`` is the only way the UI reaches
them, by name, so the whitelist ``OPS`` is the edit vocabulary.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from . import curves, edit_scope
from . import gate as gatem
from .clock import flicks_to_frames, frames_to_flicks
from .join import join_adjacent
from .messages import KuulasError
from .model import Bus, Clip, Media, Point, Project, SyncGroup, Track

#: Crossfade where a cut joins audio that was not adjacent in the source.
#: A butt splice of two unrelated samples clicks and the room tone jumps;
#: 20 ms is long enough to hide both and short enough not to smear a
#: consonant. A plain split (adjacent audio) gets none: it is already seamless.
CROSSFADE_SEC = 0.020


class EditError(KuulasError, ValueError):
    """The edit does not make sense for this project; nothing changed."""


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


# -- helpers -----------------------------------------------------------------


def _replace_track(p: Project, track: Track) -> Project:
    return replace(p, tracks=tuple(track if t.id == track.id else t for t in p.tracks))


def _replace_clip(p: Project, clip: Clip) -> Project:
    _, track = _find_clip(p, clip.id)
    clips = tuple(clip if c.id == clip.id else c for c in track.clips)
    return _replace_track(p, replace(track, clips=_sorted(clips)))


def _sorted(clips) -> tuple[Clip, ...]:
    return tuple(sorted(clips, key=lambda c: (c.start, c.id)))


def _find_clip(p: Project, clip_id: str) -> tuple[Clip, Track]:
    try:
        return p.clip_and_track(clip_id)
    except KeyError:
        raise EditError("error.edit.no_clip", clip_id=clip_id) from None


def _find_track(p: Project, track_id: str) -> Track:
    try:
        return p.track(track_id)
    except KeyError:
        raise EditError("error.edit.no_track", track_id=track_id) from None


def _points(raw) -> tuple[Point, ...]:
    return tuple(sorted((int(f), float(db)) for f, db in raw))


# -- media, tracks, buses ----------------------------------------------------


def add_media(p: Project, media: Media) -> Project:
    if any(m.id == media.id for m in p.media):
        raise EditError("error.edit.media_exists", media_id=media.id)
    return replace(p, media=(*p.media, media))


TRACK_KINDS = {"speech", "speech-mix", "music"}


def add_track(p: Project, track_id: str | None = None, name: str = "Track",
              kind: str = "speech", speaker: str = "") -> Project:
    if kind not in TRACK_KINDS:
        raise EditError("error.edit.bad_track_kind", kind=kind)
    track_id = track_id or new_id("t")
    if any(t.id == track_id for t in p.tracks):
        raise EditError("error.edit.track_exists", track_id=track_id)
    return replace(p, tracks=(*p.tracks, Track(
        id=track_id, name=name, kind=kind, speaker=speaker,
    )))


def delete_track(p: Project, track_id: str) -> Project:
    _find_track(p, track_id)
    return replace(p, tracks=tuple(t for t in p.tracks if t.id != track_id))


TRACK_FIELDS = {"name", "kind", "speaker", "bus", "gain_db", "pan", "mute", "solo"}


def set_track(p: Project, track_id: str, **fields) -> Project:
    unknown = set(fields) - TRACK_FIELDS
    if unknown:
        raise EditError("error.edit.track_no_fields", fields=", ".join(sorted(unknown)))
    if "kind" in fields and fields["kind"] not in TRACK_KINDS:
        raise EditError("error.edit.bad_track_kind", kind=fields["kind"])
    if fields.get("bus") is not None and not any(b.id == fields["bus"] for b in p.buses):
        raise EditError("error.edit.no_bus", bus_id=fields["bus"])
    if "pan" in fields:
        fields["pan"] = max(-1.0, min(1.0, float(fields["pan"])))
    return _replace_track(p, replace(_find_track(p, track_id), **fields))


def move_track(p: Project, track_id: str, index: int) -> Project:
    track = _find_track(p, track_id)
    rest = [t for t in p.tracks if t.id != track_id]
    index = max(0, min(len(rest), int(index)))
    return replace(p, tracks=(*rest[:index], track, *rest[index:]))


def set_track_automation(p: Project, track_id: str, points) -> Project:
    track = _find_track(p, track_id)
    return _replace_track(p, replace(track, automation=_points(points)))


def set_gate(p: Project, track_id: str, ranges) -> Project:
    """Replace a track's gate (WP44); ``ranges`` are normalised."""
    track = _find_track(p, track_id)
    return _replace_track(p, replace(track, gate=gatem.normalise(
        (int(a), int(b)) for a, b in ranges)))


def add_gate_range(p: Project, track_id: str, start: int, end: int) -> Project:
    track = _find_track(p, track_id)
    return _replace_track(p, replace(
        track, gate=gatem.add_range(track.gate, int(start), int(end))))


def remove_gate_range(p: Project, track_id: str, start: int, end: int) -> Project:
    """Open ``[start, end)`` again; a range spanning it falls into two."""
    track = _find_track(p, track_id)
    return _replace_track(p, replace(
        track, gate=gatem.remove_range(track.gate, int(start), int(end))))


def add_bus(p: Project, bus_id: str | None = None, name: str = "Bus") -> Project:
    bus_id = bus_id or new_id("b")
    if any(b.id == bus_id for b in p.buses):
        raise EditError("error.edit.bus_exists", bus_id=bus_id)
    return replace(p, buses=(*p.buses, Bus(id=bus_id, name=name)))


BUS_FIELDS = {"name", "gain_db", "pan", "mute"}


def set_bus(p: Project, bus_id: str, **fields) -> Project:
    unknown = set(fields) - BUS_FIELDS
    if unknown:
        raise EditError("error.edit.bus_no_fields", fields=", ".join(sorted(unknown)))
    try:
        bus = p.bus(bus_id)
    except KeyError:
        raise EditError("error.edit.no_bus", bus_id=bus_id) from None
    return replace(p, buses=tuple(replace(bus, **fields) if b.id == bus_id else b
                                  for b in p.buses))


def delete_bus(p: Project, bus_id: str) -> Project:
    p = set_bus(p, bus_id)  # existence check
    tracks = tuple(replace(t, bus=None) if t.bus == bus_id else t for t in p.tracks)
    return replace(p, buses=tuple(b for b in p.buses if b.id != bus_id), tracks=tracks)


def solo(p: Project, track_id: str, exclusive: bool = True) -> Project:
    """Solo a track, with the usual rules for a DAW.

    Exclusive (the default): soloing a track unsolos the others; soloing the
    only soloed track again clears solo. Additive: toggle this track in the
    solo set and leave the others alone.
    """
    _find_track(p, track_id)
    soloed = {t.id for t in p.tracks if t.solo}
    if exclusive:
        target = set() if soloed == {track_id} else {track_id}
    else:
        target = soloed ^ {track_id}
    return replace(p, tracks=tuple(
        replace(t, solo=t.id in target) if (t.id in target) != t.solo else t
        for t in p.tracks))


def set_master(p: Project, gain_db: float) -> Project:
    return replace(p, master_gain_db=float(gain_db))


# -- clips -------------------------------------------------------------------


def add_clip(p: Project, track_id: str, media_id: str, start: int = 0,
             offset: int = 0, length: int | None = None,
             clip_id: str | None = None) -> Project:
    track = _find_track(p, track_id)
    try:
        media = p.media_item(media_id)
    except KeyError:
        raise EditError("error.edit.no_media", media_id=media_id) from None
    if length is None:
        length = media.frames - offset
    if offset < 0 or length <= 0 or offset + length > media.frames:
        raise EditError("error.edit.clip_outside_media")
    clip = Clip(id=clip_id or new_id("c"), media=media_id, start=max(0, int(start)),
                offset=int(offset), length=int(length))
    return _replace_track(p, replace(track, clips=_sorted((*track.clips, clip))))


def delete_clip(p: Project, clip_id: str) -> Project:
    _, track = _find_clip(p, clip_id)
    return _replace_track(p, replace(track, clips=tuple(c for c in track.clips
                                                        if c.id != clip_id)))


def move_clip(p: Project, clip_id: str, start: int,
              track_id: str | None = None) -> Project:
    clip, track = _find_clip(p, clip_id)
    moved = replace(clip, start=max(0, int(start)))
    if track_id is None or track_id == track.id:
        return _replace_clip(p, moved)
    target = _find_track(p, track_id)
    p = delete_clip(p, clip_id)
    return _replace_track(p, replace(target, clips=_sorted((*target.clips, moved))))


def trim_clip(p: Project, clip_id: str, start: int | None = None,
              end: int | None = None) -> Project:
    """Move a clip's edges on the timeline; the audio under them stays put."""
    clip, _ = _find_clip(p, clip_id)
    media = p.media_item(clip.media)
    new_start, new_end = clip.start, clip.end
    if start is not None:
        # The left edge cannot reach before the media's first frame.
        new_start = max(int(start), clip.start - clip.offset, 0)
    if end is not None:
        new_end = min(int(end), clip.start - clip.offset + media.frames)
    if new_end - new_start <= 0:
        raise EditError("error.edit.trim_empty")
    offset = clip.offset + (new_start - clip.start)
    length = new_end - new_start
    return _replace_clip(p, replace(
        clip, start=new_start, offset=offset, length=length,
        fade_in=min(clip.fade_in, length), fade_out=min(clip.fade_out, length),
        xfade_in=clip.xfade_in if new_start == clip.start else 0,
        xfade_out=clip.xfade_out if new_end == clip.end else 0))


def split_clip(p: Project, clip_id: str, at: int, new_id: str | None = None) -> Project:
    clip, track = _find_clip(p, clip_id)
    at = int(at)
    if not clip.start < at < clip.end:
        raise EditError("error.edit.split_outside")
    left, right = _cut(clip, at, new_id or globals()["new_id"]("c"))
    clips = [c for c in track.clips if c.id != clip_id] + [left, right]
    return _replace_track(p, replace(track, clips=_sorted(clips)))


def _cut(clip: Clip, at: int, right_id: str) -> tuple[Clip, Clip]:
    head = at - clip.start
    left = replace(clip, length=head, fade_out=0, fade_in=min(clip.fade_in, head),
                   xfade_out=0)
    right = replace(clip, id=right_id, start=at, offset=clip.offset + head,
                    length=clip.length - head, fade_in=0, xfade_in=0,
                    fade_out=min(clip.fade_out, clip.length - head))
    return left, right


CLIP_FIELDS = {"gain_db", "pan", "fade_in", "fade_out", "muted", "name"}


def set_clip(p: Project, clip_id: str, **fields) -> Project:
    unknown = set(fields) - CLIP_FIELDS
    if unknown:
        raise EditError("error.edit.clip_no_fields", fields=", ".join(sorted(unknown)))
    clip, _ = _find_clip(p, clip_id)
    if "pan" in fields:
        fields["pan"] = max(-1.0, min(1.0, float(fields["pan"])))
    for name in ("fade_in", "fade_out"):
        if name in fields:
            fields[name] = max(0, min(clip.length, int(fields[name])))
    if "name" in fields:
        fields["name"] = str(fields["name"]).strip()[:200]
    return _replace_clip(p, replace(clip, **fields))


def set_clip_envelope(p: Project, clip_id: str, points) -> Project:
    clip, _ = _find_clip(p, clip_id)
    return _replace_clip(p, replace(clip, envelope=_points(points)))


def set_clip_extra(p: Project, clip_id: str, key: str, value) -> Project:
    clip, _ = _find_clip(p, clip_id)
    return _replace_clip(p, replace(clip, extra={**clip.extra, key: value}))


def set_track_extra(p: Project, track_id: str, key: str, value) -> Project:
    track = _find_track(p, track_id)
    return _replace_track(p, replace(track, extra={**track.extra, key: value}))


def mute_ranges(p: Project, track_id: str, ranges) -> Project:
    """Split a track's clips at each range's edges and mute what lies inside.

    The splits are of adjacent audio, so they get no crossfade; nothing
    moves. Muted pieces stay visible and a single unmute brings any of them
    back exactly: the 30 ms ramp on the open neighbours is derived by the
    mixer (``mixer.MUTE_RAMP_SEC``), never stored.
    """
    track = _find_track(p, track_id)
    edges = sorted({int(x) for a, b in ranges for x in (a, b)})
    clips = list(track.clips)
    for edge in edges:
        nxt = []
        for c in clips:
            if c.start < edge < c.end:
                nxt.extend(_cut(c, edge, new_id("c")))
            else:
                nxt.append(c)
        clips = nxt
    spans = [(int(a), int(b)) for a, b in ranges]

    def inside(c: Clip) -> bool:
        return any(a <= c.start and c.end <= b for a, b in spans)

    clips = _sorted(replace(c, muted=True) if inside(c) else c for c in clips)
    return _replace_track(p, replace(track, clips=clips))


def restore_cuts(p: Project, clip_ids: list[str]) -> Project:
    """Unmute the listed clips, then join each with its neighbours where contiguous.

    Only the immediate left and right neighbours of restored clips are considered
    for joining, leaving unrelated split clips elsewhere on the track intact.
    """
    target_ids = set(clip_ids)
    if not target_ids:
        return p

    tracks = []
    for track in p.tracks:
        track_clip_ids = {c.id for c in track.clips}
        in_track = target_ids & track_clip_ids
        if not in_track:
            tracks.append(track)
            continue

        clips = list(_sorted(track.clips))
        # 1. Unmute restored clips
        clips = [replace(c, muted=False) if c.id in in_track else c for c in clips]

        # 2. Collect affected indices (each restored clip + immediate left & right)
        n = len(clips)
        affected = set()
        for i, c in enumerate(clips):
            if c.id in in_track:
                affected.add(i)
                if i > 0:
                    affected.add(i - 1)
                if i + 1 < n:
                    affected.add(i + 1)

        # 3. Partition affected indices into contiguous ranges [start, end)
        ranges: list[tuple[int, int]] = []
        sorted_affected = sorted(affected)
        r_start = sorted_affected[0]
        r_end = r_start + 1
        for idx in sorted_affected[1:]:
            if idx == r_end:
                r_end += 1
            else:
                ranges.append((r_start, r_end))
                r_start = idx
                r_end = r_start + 1
        ranges.append((r_start, r_end))

        # 4. Reconstruct track clips
        new_clips: list[Clip] = []
        last_pos = 0
        for start, end in ranges:
            new_clips.extend(clips[last_pos:start])
            new_clips.extend(join_adjacent(clips[start:end]))
            last_pos = end
        new_clips.extend(clips[last_pos:])

        tracks.append(replace(track, clips=tuple(new_clips)))

    return replace(p, tracks=tuple(tracks))


# -- selections --------------------------------------------------------------


def clips_from(p: Project, frame: int, track_id: str | None = None) -> list[str]:
    """Clips that play at or after ``frame``: Hindenburg's Shift(+Option)+End."""
    return [c.id for t in p.tracks if track_id in (None, t.id)
            for c in t.clips if c.end > frame]


def clips_until(p: Project, frame: int, track_id: str | None = None) -> list[str]:
    """Clips that play at or before ``frame``: Shift(+Option)+Home."""
    return [c.id for t in p.tracks if track_id in (None, t.id)
            for c in t.clips if c.start <= frame]


def shift_clips(p: Project, clip_ids, delta: int) -> Project:
    """Move several clips by the same amount, keeping their spacing.

    If the earliest would cross zero, the whole selection stops there.
    """
    ids = set(clip_ids)
    chosen = [c for t in p.tracks for c in t.clips if c.id in ids]
    if not chosen:
        raise EditError("error.edit.no_selection")
    delta = max(int(delta), -min(c.start for c in chosen))
    tracks = tuple(
        replace(t, clips=_sorted(replace(c, start=c.start + delta) if c.id in ids else c
                                 for c in t.clips))
        for t in p.tracks)
    return replace(p, tracks=tracks)


def set_clips(p: Project, clip_ids, **fields) -> Project:
    for clip_id in clip_ids:
        p = set_clip(p, clip_id, **fields)
    return p


def delete_clips(p: Project, clip_ids) -> Project:
    for clip_id in clip_ids:
        p = delete_clip(p, clip_id)
    return p


# -- the editing keys (WP5): several clips or tracks, one undo step ----------

#: The inspector's clip gain range; the keys stay inside it.
CLIP_GAIN_RANGE = (-60.0, 12.0)


def split_clips(p: Project, at: int, clip_ids) -> Project:
    """Split each listed clip that the point lies inside; skip the others."""
    at = int(at)
    hit = [cid for cid in clip_ids if (c := _find_clip(p, cid)[0]).start < at < c.end]
    if not hit:
        raise EditError("error.edit.split_outside")
    for clip_id in hit:
        p = split_clip(p, clip_id, at)
    return p


def mute_range(p: Project, start: int, end: int, track_ids,
               group_editing: bool = False) -> Project:
    """Soft-cut ``[start, end)``: mute it in place on the tracks (the sync
    group's too when ``group_editing``), leaving the gap. Nothing moves."""
    start, end = int(start), int(end)
    if end <= start:
        raise EditError("error.edit.empty_range")
    for track_id in edit_scope.expand_range(p, None, list(track_ids), start, end,
                                            group_editing):
        p = mute_ranges(p, track_id, [(start, end)])
    return p


def cut_range(p: Project, start: int, end: int, track_ids,
              group_editing: bool = False) -> Project:
    """Ripple-delete ``[start, end)`` on the tracks, or on the sync group's
    tracks when ``group_editing`` (tracks in no group: all, as in WP19a)."""
    start, end = int(start), int(end)
    if end <= start:
        raise EditError("error.edit.empty_range")
    return ripple_delete(p, start, end, edit_scope.expand_range(
        p, None, list(track_ids), start, end, group_editing))


def nudge_clips(p: Project, clip_ids, delta: int, group_editing: bool = False) -> Project:
    """``shift_clips`` that takes the clips' sync partners along when
    ``group_editing`` is on."""
    return shift_clips(p, edit_scope.expand_clips(p, None, list(clip_ids), group_editing),
                       delta)


def trim_clips(p: Project, clip_ids, start: int | None = None,
               end: int | None = None) -> Project:
    """``trim_clip`` on several clips; one that would end up empty refuses all."""
    for clip_id in clip_ids:
        p = trim_clip(p, clip_id, start=start, end=end)
    return p


def adjust_clip_gain(p: Project, clip_ids, delta_db: float) -> Project:
    """Add ``delta_db`` to each clip's gain, within the inspector's range."""
    clip_ids = list(clip_ids)
    if not clip_ids:
        raise EditError("error.edit.no_selection")
    low, high = CLIP_GAIN_RANGE
    for clip_id in clip_ids:
        gain = _find_clip(p, clip_id)[0].gain_db + float(delta_db)
        p = set_clip(p, clip_id, gain_db=round(max(low, min(high, gain)), 2))
    return p


# -- sync groups -------------------------------------------------------------


def mark_in_sync(p: Project, clip_ids, main: str, group_id: str | None = None,
                 basis: str = "timeline") -> Project:
    """Declare these clips in sync with ``main``.

    ``basis="timeline"``: the selected clips are in sync *as they sit now*;
    pick any that are still right. ``basis="files"``: trust the files' own
    clocks (BWF time reference; files without one started together), so
    sync can be set up late, after the timeline has drifted.

    Either way the whole file joins: membership is per media (docs/FORMAT.md),
    so every clip cut from it shares its clock, and pieces that were never
    selected (the ones that drifted) can be resynced too. A media is in one
    group at a time: marking moves it out of any other. From then on
    ``resync`` puts any of them back.
    """
    if basis not in ("timeline", "files"):
        raise EditError("error.edit.sync_basis", basis=basis)
    group_id = group_id or new_id("g")
    main_clip, _ = _find_clip(p, main)
    main_media = p.media_item(main_clip.media)
    base = main_clip.start - main_clip.offset
    origins: dict[str, int] = {main_clip.media: 0}  # flicks
    for clip_id in clip_ids:
        c, _ = _find_clip(p, clip_id)
        if c.media in origins:
            continue
        if basis == "files":
            origins[c.media] = ((p.media_item(c.media).time_ref_flicks or 0)
                                - (main_media.time_ref_flicks or 0))
        else:
            origins[c.media] = frames_to_flicks((c.start - c.offset) - base, p.rate)
    kept: dict[str, int] = {}
    groups = []
    for g in p.sync_groups:
        rest = tuple((m, o) for m, o in g.members if m not in origins)
        if g.id == group_id:
            kept = dict(rest)  # re-marking a group keeps members not marked again
        elif rest:
            groups.append(replace(g, members=rest))
    marked = SyncGroup(id=group_id, main=main_clip.media,
                       members=tuple(sorted({**kept, **origins}.items())))
    return replace(p, sync_groups=(*groups, marked))


def _recorded(p: Project, clip: Clip) -> int:
    """Where ``clip``'s first frame sits on its group's recording clock, in
    project frames."""
    member = p.sync_member(clip.media)
    origin = 0 if member is None else flicks_to_frames(member[1], p.rate)
    return clip.offset + origin


def resync(p: Project, clip_ids) -> Project:
    """Move each clip back into sync with the main clip's piece it belongs with.

    The reference is the main media's piece that plays the same stretch of
    the recording, so cuts made in the main clip are followed. Clips without
    a group, and the main media's own pieces, stay where they are.
    """
    for clip_id in clip_ids:
        c, _ = _find_clip(p, clip_id)
        group = p.sync_group(c.media)
        if group is None or c.media == group.main:
            continue
        refs = [r for t in p.tracks for r in t.clips if r.media == group.main]
        if not refs:
            continue
        rec = _recorded(p, c)

        def score(r: Clip, rec: int = rec, c: Clip = c,
                  p: Project = p) -> tuple[int, int]:
            r_rec = _recorded(p, r)
            overlap = min(r_rec + r.length, rec + c.length) - max(r_rec, rec)
            return (overlap if overlap > 0 else overlap * 2, -abs(r.start - c.start))

        ref = max(refs, key=score)
        start = ref.start + (rec - _recorded(p, ref))
        p = _replace_clip(p, replace(c, start=max(0, start)))
    return p


# -- ripple ------------------------------------------------------------------


def ripple_delete(p: Project, start: int, end: int,
                  track_ids: list[str] | None = None) -> Project:
    """Remove ``[start, end)`` from the timeline and close the gap.

    This is the transcript edit: deleting words cuts the same stretch from
    every track, so the speakers stay in sync.
    """
    start, end = int(start), int(end)
    if end <= start:
        raise EditError("error.edit.empty_range")
    gap = end - start
    scope = set(track_ids) if track_ids is not None else {t.id for t in p.tracks}
    tracks = []
    for track in p.tracks:
        if track.id not in scope:
            tracks.append(track)
            continue
        clips: list[Clip] = []
        left = right = None
        for c in track.clips:
            if c.end <= start:
                clips.append(c)
            elif c.start >= end:
                clips.append(replace(c, start=c.start - gap))
            else:
                if c.start < start:
                    left, _ = _cut(c, start, "")
                    clips.append(left)
                if c.end > end:
                    _, right = _cut(c, end, c.id if c.start >= start else new_id("c"))
                    right = replace(right, start=start)
                    clips.append(right)
        if left is not None and right is not None:
            clips = _crossfade(p, clips, left, right)
        tracks.append(replace(track, clips=_sorted(clips),
                              automation=_ripple_points(track.automation, start, end),
                              gate=gatem.ripple(track.gate, start, end)))
    return replace(p, tracks=tuple(tracks))


def _crossfade(p: Project, clips: list[Clip], left: Clip, right: Clip) -> list[Clip]:
    """Centre a crossfade on the join of ``left`` and ``right``.

    Each side plays half the fade from audio beyond its edge, so the length
    is limited by how much source each has there; both use the same length,
    which is what keeps the summed gain constant.
    """
    if left.muted or right.muted:
        return clips
    tail = p.media_item(left.media).frames - (left.offset + left.length)
    head = right.offset
    xf = min(round(CROSSFADE_SEC * p.rate), 2 * tail, 2 * head,
             left.length, right.length)
    xf -= xf % 2
    if xf <= 0:
        return clips
    out = []
    for clip in clips:
        edited = clip
        if clip is left:
            edited = replace(clip, xfade_out=xf)
        elif clip is right:
            edited = replace(clip, xfade_in=xf)
        out.append(edited)
    return out


def _ripple_points(points, start: int, end: int) -> tuple[Point, ...]:
    if not points:
        return ()
    gap = end - start
    before = [pt for pt in points if pt[0] < start]
    after = [(f - gap, db) for f, db in points if f >= end]
    joint = [(start, curves.value_at(points, start)),
             (start, curves.value_at(points, end))]
    out: list[Point] = []
    for pt in [*before, *joint, *after]:
        if not out or out[-1] != pt:
            out.append(pt)
    return tuple(out)


# -- dispatch ----------------------------------------------------------------

OPS = {
    f.__name__: f
    for f in (
        add_track, delete_track, set_track, solo, move_track, set_track_automation,
        add_bus, set_bus, delete_bus, set_master,
        add_clip, delete_clip, move_clip, trim_clip, split_clip, set_clip,
        set_clip_envelope, ripple_delete, mute_ranges,
        set_gate, add_gate_range, remove_gate_range,
        shift_clips, set_clips, delete_clips, mark_in_sync, resync,
        split_clips, mute_range, cut_range, nudge_clips, trim_clips, adjust_clip_gain,
        restore_cuts,
    )
}


def apply(p: Project, name: str, args: dict) -> Project:
    try:
        op = OPS[name]
    except KeyError:
        raise EditError("error.edit.unknown", name=name) from None
    try:
        return op(p, **args)
    except TypeError as e:
        raise EditError("error.edit.bad_arguments", name=name, detail=str(e)) from None
