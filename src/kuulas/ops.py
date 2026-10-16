"""Edits: pure functions ``Project -> Project``.

Each one is a single undo step. ``apply`` is the only way the UI reaches
them, by name, so the whitelist ``OPS`` is the edit vocabulary.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from . import curves
from .model import Bus, Clip, Media, Point, Project, Track

#: Crossfade where a cut joins audio that was not adjacent in the source.
#: A butt splice of two unrelated samples clicks and the room tone jumps;
#: 20 ms is long enough to hide both and short enough not to smear a
#: consonant. A plain split (adjacent audio) gets none: it is already seamless.
CROSSFADE_SEC = 0.020


class EditError(ValueError):
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
        raise EditError(f"no clip {clip_id}") from None


def _find_track(p: Project, track_id: str) -> Track:
    try:
        return p.track(track_id)
    except KeyError:
        raise EditError(f"no track {track_id}") from None


def _points(raw) -> tuple[Point, ...]:
    return tuple(sorted((int(f), float(db)) for f, db in raw))


# -- media, tracks, buses ----------------------------------------------------


def add_media(p: Project, media: Media) -> Project:
    if any(m.id == media.id for m in p.media):
        raise EditError(f"media {media.id} already in project")
    return replace(p, media=(*p.media, media))


def add_track(p: Project, track_id: str | None = None, name: str = "Track",
              kind: str = "speech") -> Project:
    track_id = track_id or new_id("t")
    if any(t.id == track_id for t in p.tracks):
        raise EditError(f"track {track_id} exists")
    return replace(p, tracks=(*p.tracks, Track(id=track_id, name=name, kind=kind)))


def delete_track(p: Project, track_id: str) -> Project:
    _find_track(p, track_id)
    return replace(p, tracks=tuple(t for t in p.tracks if t.id != track_id))


TRACK_FIELDS = {"name", "kind", "bus", "gain_db", "pan", "mute", "solo"}


def set_track(p: Project, track_id: str, **fields) -> Project:
    unknown = set(fields) - TRACK_FIELDS
    if unknown:
        raise EditError(f"track has no {sorted(unknown)}")
    if fields.get("bus") is not None and not any(b.id == fields["bus"] for b in p.buses):
        raise EditError(f"no bus {fields['bus']}")
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


def add_bus(p: Project, bus_id: str | None = None, name: str = "Bus") -> Project:
    bus_id = bus_id or new_id("b")
    if any(b.id == bus_id for b in p.buses):
        raise EditError(f"bus {bus_id} exists")
    return replace(p, buses=(*p.buses, Bus(id=bus_id, name=name)))


BUS_FIELDS = {"name", "gain_db", "pan", "mute"}


def set_bus(p: Project, bus_id: str, **fields) -> Project:
    unknown = set(fields) - BUS_FIELDS
    if unknown:
        raise EditError(f"bus has no {sorted(unknown)}")
    try:
        bus = p.bus(bus_id)
    except KeyError:
        raise EditError(f"no bus {bus_id}") from None
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


def set_transcript(p: Project, media_id: str, rev: int) -> Project:
    rest = tuple((m, r) for m, r in p.transcripts if m != media_id)
    return replace(p, transcripts=(*rest, (media_id, int(rev))))


# -- clips -------------------------------------------------------------------


def add_clip(p: Project, track_id: str, media_id: str, start: int = 0,
             offset: int = 0, length: int | None = None,
             clip_id: str | None = None) -> Project:
    track = _find_track(p, track_id)
    try:
        media = p.media_item(media_id)
    except KeyError:
        raise EditError(f"no media {media_id}") from None
    if length is None:
        length = media.frames - offset
    if offset < 0 or length <= 0 or offset + length > media.frames:
        raise EditError("clip reaches outside its media")
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
        raise EditError("trim would leave an empty clip")
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
        raise EditError("split point is not inside the clip")
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


CLIP_FIELDS = {"gain_db", "pan", "fade_in", "fade_out", "muted"}


def set_clip(p: Project, clip_id: str, **fields) -> Project:
    unknown = set(fields) - CLIP_FIELDS
    if unknown:
        raise EditError(f"clip has no {sorted(unknown)}")
    clip, _ = _find_clip(p, clip_id)
    if "pan" in fields:
        fields["pan"] = max(-1.0, min(1.0, float(fields["pan"])))
    for name in ("fade_in", "fade_out"):
        if name in fields:
            fields[name] = max(0, min(clip.length, int(fields[name])))
    return _replace_clip(p, replace(clip, **fields))


def set_clip_envelope(p: Project, clip_id: str, points) -> Project:
    clip, _ = _find_clip(p, clip_id)
    return _replace_clip(p, replace(clip, envelope=_points(points)))


#: Fade on an open piece next to a muted one. A gate that snaps shut on
#: room tone clicks; 30 ms is inaudible as a fade and the mask already
#: holds the mic open past the last word (``masks.DUCK_HOLD``).
MUTE_FADE_SEC = 0.030


def mute_ranges(p: Project, track_id: str, ranges) -> Project:
    """Split a track's clips at each range's edges and mute what lies inside.

    The splits are of adjacent audio, so they get no crossfade; nothing
    moves. This is how Auto-Silence lands: muted pieces stay visible and a
    single unmute brings any of them back.
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

    fade = round(MUTE_FADE_SEC * p.rate)
    clips = _sorted(replace(c, muted=True) if inside(c) else c for c in clips)
    muted_edges = {c.start for c in clips if c.muted} | {c.end for c in clips if c.muted}
    out = []
    for clip in clips:
        edited = clip
        if not clip.muted:
            if clip.end in muted_edges:
                edited = replace(
                    edited, fade_out=max(clip.fade_out, min(fade, clip.length)))
            if clip.start in muted_edges:
                edited = replace(
                    edited, fade_in=max(clip.fade_in, min(fade, clip.length)))
        out.append(edited)
    return _replace_track(p, replace(track, clips=tuple(out)))


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
        raise EditError("no clips selected")
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


# -- sync groups -------------------------------------------------------------


def mark_in_sync(p: Project, clip_ids, main: str, group_id: str | None = None,
                 basis: str = "timeline") -> Project:
    """Declare these clips in sync with ``main``.

    ``basis="timeline"``: the selected clips are in sync *as they sit now*;
    pick any that are still right. ``basis="files"``: trust the files' own
    clocks (BWF time reference; files without one started together), so
    sync can be set up late, after the timeline has drifted.

    Either way the whole file joins: every clip cut from the same media
    shares its clock, so pieces that were never selected (the ones that
    drifted) can be resynced too. From then on ``resync`` puts any of them back.
    """
    if basis not in ("timeline", "files"):
        raise EditError(f"unknown sync basis {basis!r}")
    group_id = group_id or new_id("g")
    main_clip, _ = _find_clip(p, main)
    main_media = p.media_item(main_clip.media)
    base = main_clip.start - main_clip.offset
    origins: dict[str, int] = {main_clip.media: 0}
    for clip_id in clip_ids:
        c, _ = _find_clip(p, clip_id)
        if c.media in origins:
            continue
        if basis == "files":
            origins[c.media] = p.media_item(c.media).time_ref - main_media.time_ref
        else:
            origins[c.media] = (c.start - c.offset) - base
    tracks = tuple(
        replace(t, clips=tuple(
            replace(c, sync=group_id, sync_origin=origins[c.media])
            if c.media in origins else c for c in t.clips))
        for t in p.tracks)
    groups = tuple(g for g in p.sync_groups if g[0] != group_id)
    return replace(p, tracks=tracks, sync_groups=(*groups, (group_id, main_clip.media)))


def resync(p: Project, clip_ids) -> Project:
    """Move each clip back into sync with the main clip's piece it belongs with.

    The reference is the main-clip piece that plays the same stretch of the
    recording, so cuts made in the main clip are followed. Clips without a
    group, and the main clip's own pieces, stay where they are.
    """
    mains = dict(p.sync_groups)
    for clip_id in clip_ids:
        c, _ = _find_clip(p, clip_id)
        main_media = mains.get(c.sync) if c.sync else None
        if main_media is None or c.media == main_media:
            continue
        refs = [r for t in p.tracks for r in t.clips
                if r.sync == c.sync and r.media == main_media]
        if not refs:
            continue

        def score(r: Clip, c: Clip = c) -> tuple[int, int]:
            overlap = (min(r.recorded + r.length, c.recorded + c.length)
                       - max(r.recorded, c.recorded))
            return (overlap if overlap > 0 else overlap * 2, -abs(r.start - c.start))

        ref = max(refs, key=score)
        start = ref.start + (c.recorded - ref.recorded)
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
        raise EditError("empty range")
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
                              automation=_ripple_points(track.automation, start, end)))
    return replace(p, tracks=tuple(tracks))


def _crossfade(p: Project, clips: list[Clip], left: Clip, right: Clip) -> list[Clip]:
    """Centre a crossfade on the join of ``left`` and ``right``.

    Each side plays half the fade from audio beyond its edge, so the length
    is limited by how much source each has there; both use the same length,
    which is what keeps the summed gain constant.
    """
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
        shift_clips, set_clips, delete_clips, mark_in_sync, resync,
    )
}


def apply(p: Project, name: str, args: dict) -> Project:
    try:
        op = OPS[name]
    except KeyError:
        raise EditError(f"unknown edit {name!r}") from None
    try:
        return op(p, **args)
    except TypeError as e:
        raise EditError(f"{name}: {e}") from None
