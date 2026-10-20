"""Edits: pure functions ``Project -> Project``.

Each one is a single undo step. ``apply`` is the only way the UI reaches
them, by name, so the whitelist ``OPS`` is the edit vocabulary.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from . import curves, edit_scope, narration
from . import gate as gatem
from . import markers as markersm
from . import placeholders as placeholdersm
from .clock import flicks_to_frames, frames_to_flicks
from .join import join_adjacent
from .messages import KuulasError
from .model import Bus, Clip, Marker, Media, Placeholder, Point, Project, SyncGroup, Track

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


TRACK_KINDS = {"speech", "music"}


def add_track(p: Project, track_id: str | None = None, name: str = "Track",
              kind: str = "speech", speaker: str = "",
              bus: str | None = None) -> Project:
    if kind not in TRACK_KINDS:
        raise EditError("error.edit.bad_track_kind", kind=kind)
    track_id = track_id or new_id("t")
    if any(t.id == track_id for t in p.tracks):
        raise EditError("error.edit.track_exists", track_id=track_id)
    p = replace(p, tracks=(*p.tracks, Track(
        id=track_id, name=name, kind=kind, speaker=speaker,
    )))
    # On a bus with a role the new track follows it (set_track's rule for a move).
    return p if bus is None else set_track(p, track_id, bus=bus)


def delete_empty_tracks(p: Project) -> Project:
    """Remove every track that holds no clip (a track made first, then emptied by moving
    its clips elsewhere). Tracks with clips stay, in order. None empty is an error."""
    empty = [t.id for t in p.tracks if not t.clips]
    if not empty:
        raise EditError("error.edit.no_empty_tracks")
    for track_id in empty:
        p = delete_track(p, track_id)
    return p


def delete_track(p: Project, track_id: str) -> Project:
    _find_track(p, track_id)
    return replace(p, tracks=tuple(t for t in p.tracks if t.id != track_id),
                   placeholders=tuple(h for h in p.placeholders if h.track != track_id))


TRACK_FIELDS = {"name", "kind", "speaker", "bus", "gain_db", "pan", "mute", "solo",
                "target_lufs", "mono", "follow_bus_role"}


def set_track(p: Project, track_id: str, **fields) -> Project:
    unknown = set(fields) - TRACK_FIELDS
    if unknown:
        raise EditError("error.edit.track_no_fields", fields=", ".join(sorted(unknown)))
    if "kind" in fields and fields["kind"] not in TRACK_KINDS:
        raise EditError("error.edit.bad_track_kind", kind=fields["kind"])
    if fields.get("bus") is not None and not any(b.id == fields["bus"] for b in p.buses):
        raise EditError("error.edit.no_bus", bus_id=fields["bus"])
    # Bus roles. Invariant: follow_bus_role implies kind == the bus's role.
    track = _find_track(p, track_id)
    bus_after = fields.get("bus", track.bus)
    role = next((b.kind for b in p.buses if b.id == bus_after), None)
    if "follow_bus_role" in fields:
        fields["follow_bus_role"] = bool(fields["follow_bus_role"])
        if fields["follow_bus_role"]:
            if role is None:
                raise EditError("error.edit.no_bus_role")
            fields["kind"] = role
    elif "bus" in fields:
        # A move onto a bus with a role follows it (an explicit kind is an override);
        # onto a bus without one, or off a bus, the track follows nothing.
        follow = role is not None and "kind" not in fields
        fields["follow_bus_role"] = follow
        if follow:
            fields["kind"] = role
    elif "kind" in fields:
        fields["follow_bus_role"] = False  # set by hand: an override
    if "pan" in fields:
        fields["pan"] = max(-1.0, min(1.0, float(fields["pan"])))
    if "mono" in fields:
        fields["mono"] = bool(fields["mono"])
    if fields.get("target_lufs") is not None:
        fields["target_lufs"] = _target_lufs(fields["target_lufs"])
    return _replace_track(p, replace(_find_track(p, track_id), **fields))


#: A loudness target outside this is a typo (-70 is the BS.1770 gate floor).
TARGET_LUFS_RANGE = (-70.0, 0.0)


def _target_lufs(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = float("nan")
    if not (TARGET_LUFS_RANGE[0] <= v <= TARGET_LUFS_RANGE[1]):  # also false for nan
        raise EditError("error.edit.bad_arguments", name="set_track",
                        detail=f"target_lufs {value!r}")
    return v


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


def add_bus(p: Project, bus_id: str | None = None, name: str = "Bus",
            track_ids=()) -> Project:
    """Add a bus, and route ``track_ids`` to it in the same edit (one undo step)."""
    bus_id = bus_id or new_id("b")
    if any(b.id == bus_id for b in p.buses):
        raise EditError("error.edit.bus_exists", bus_id=bus_id)
    p = replace(p, buses=(*p.buses, Bus(id=bus_id, name=name)))
    for track_id in track_ids:
        p = set_track(p, track_id, bus=bus_id)
    return p


BUS_FIELDS = {"name", "gain_db", "pan", "mute", "kind"}


def set_bus(p: Project, bus_id: str, **fields) -> Project:
    unknown = set(fields) - BUS_FIELDS
    if unknown:
        raise EditError("error.edit.bus_no_fields", fields=", ".join(sorted(unknown)))
    try:
        bus = p.bus(bus_id)
    except KeyError:
        raise EditError("error.edit.no_bus", bus_id=bus_id) from None
    if fields.get("kind") is not None and fields["kind"] not in TRACK_KINDS:
        raise EditError("error.edit.bad_track_kind", kind=fields["kind"])
    p = replace(p, buses=tuple(replace(bus, **fields) if b.id == bus_id else b
                               for b in p.buses))
    if "kind" in fields:
        # The role goes to every track on the bus through set_track, the one path
        # that changes a track's kind (also when the role is unchanged: that is how
        # an override is put right). A cleared role leaves the kinds, ends following.
        for track in p.tracks:
            if track.bus == bus_id:
                if fields["kind"] is None:
                    p = _replace_track(p, replace(track, follow_bus_role=False))
                else:
                    p = set_track(p, track.id, follow_bus_role=True)
    return p


def delete_bus(p: Project, bus_id: str) -> Project:
    p = set_bus(p, bus_id)  # existence check
    tracks = tuple(replace(t, bus=None, follow_bus_role=False) if t.bus == bus_id else t
                   for t in p.tracks)
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


def reset_gains(p: Project) -> Project:
    """Set every track's and every bus's ``gain_db`` to 0 (unity), in one step, so the
    levels can be judged before export. The master, clip gains and pan stay. Nothing to
    reset is an error, so the menu can say so."""
    if all(x.gain_db == 0 for x in (*p.tracks, *p.buses)):
        raise EditError("error.edit.no_gains_to_reset")
    return replace(
        p,
        tracks=tuple(replace(t, gain_db=0.0) if t.gain_db != 0 else t for t in p.tracks),
        buses=tuple(replace(b, gain_db=0.0) if b.gain_db != 0 else b for b in p.buses))


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
    # Remember the track it came from (the first one; back home forgets it).
    home = clip.home if clip.home is not None else track.id
    moved = replace(moved, home=None if home == track_id else home)
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


# -- groups and merge ---------------------------------------------------------


def _map_clips(p: Project, change) -> Project:
    """``p`` with ``change(clip)`` applied to every clip of every track."""
    return replace(p, tracks=tuple(
        replace(t, clips=tuple(change(c) for c in t.clips)) for t in p.tracks))


def group_clips(p: Project, clip_ids) -> Project:
    """Put the clips in one new group. A clip already in a group leaves it
    (the rest of that group stays together)."""
    ids = list(dict.fromkeys(clip_ids))
    if len(ids) < 2:
        raise EditError("error.edit.bad_arguments", name="group_clips",
                        detail="a group needs at least 2 clips")
    for clip_id in ids:
        _find_clip(p, clip_id)
    group = new_id("g")
    wanted = set(ids)
    return _map_clips(p, lambda c: replace(c, group=group) if c.id in wanted else c)


def ungroup_clips(p: Project, clip_ids) -> Project:
    """Dissolve the groups the clips belong to: every member is ungrouped."""
    dissolved = {g for cid in clip_ids if (g := _find_clip(p, cid)[0].group) is not None}
    return _map_clips(p, lambda c: replace(c, group=None) if c.group in dissolved else c)


def merge_clips(p: Project, clip_ids) -> Project:
    """Join the selected clips that ``join_adjacent`` would join, per track.

    Lossless: nothing leaves the source media, and a split at the old boundary
    gives the old clips back (group, name and gain carry over to both halves).
    Clips that cannot be joined stay as they are; refused when none can.
    """
    wanted = set(clip_ids)
    for clip_id in wanted:
        _find_clip(p, clip_id)
    tracks = []
    changed = False
    for track in p.tracks:
        picked = [c for c in track.clips if c.id in wanted]
        joined = join_adjacent(picked)
        if len(joined) == len(picked):
            tracks.append(track)
            continue
        changed = True
        names = {c.id: c.name for c in picked}
        rest = [c for c in track.clips if c.id not in wanted]
        # The joined clip keeps the first clip's id, so it keeps its name too.
        joined = [replace(c, name=names[c.id]) for c in joined]
        tracks.append(replace(track, clips=_sorted([*rest, *joined])))
    if not changed:
        raise EditError("error.edit.merge_nothing")
    return replace(p, tracks=tuple(tracks))


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


def set_fade_at(p: Project, clip_id: str, frame: int,
                side: str | None = None) -> Project:
    clip, _ = _find_clip(p, clip_id)
    frame = int(frame)
    if not (clip.start <= frame < clip.end):
        raise EditError("error.edit.split_outside")

    if side is None:
        effective_side = "in" if frame - clip.start <= clip.end - frame else "out"
    elif side in ("in", "fade_in"):
        effective_side = "in"
    elif side in ("out", "fade_out"):
        effective_side = "out"
    else:
        raise EditError("error.edit.bad_arguments", name="set_fade_at",
                        detail=f"unknown side: {side}")

    if effective_side == "in":
        new_fade_in = max(0, min(clip.length, int(frame - clip.start)))
        if new_fade_in + clip.fade_out > clip.length:
            new_fade_out = max(0, clip.length - new_fade_in)
        else:
            new_fade_out = clip.fade_out
    else:
        new_fade_out = max(0, min(clip.length, int(clip.end - frame)))
        if clip.fade_in + new_fade_out > clip.length:
            new_fade_in = max(0, clip.length - new_fade_out)
        else:
            new_fade_in = clip.fade_in

    return _replace_clip(p, replace(clip, fade_in=new_fade_in, fade_out=new_fade_out))


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


def mute_range(p: Project, start: int, end: int, track_ids=None) -> Project:
    """Soft-cut ``[start, end)``: mute it in place on the tracks (``None``: all
    tracks, ``edit_scope.range_tracks``), leaving the gap. Nothing moves."""
    start, end = int(start), int(end)
    if end <= start:
        raise EditError("error.edit.empty_range")
    for track_id in _range_tracks(p, track_ids):
        p = mute_ranges(p, track_id, [(start, end)])
    return p


def _range_tracks(p: Project, track_ids) -> list[str]:
    """``edit_scope.range_tracks`` with an unknown track as an ``EditError``."""
    try:
        return edit_scope.range_tracks(p, track_ids)
    except KeyError as e:
        raise EditError("error.edit.no_track", track_id=e.args[0]) from None


def clear_range(p: Project, start: int, end: int, track_ids=None) -> Project:
    """Delete ``[start, end)`` on the tracks (``None``: all tracks)
    and LEAVE the gap: the clips on either side keep their places and the audio keeps its
    place in its recording. Nothing moves; markers, automation and gates are untouched.
    Lift-cut's removal (owner, 2026-10-19: Alt+X must delete, not mute)."""
    start, end = int(start), int(end)
    if end <= start:
        raise EditError("error.edit.empty_range")
    scope = set(_range_tracks(p, track_ids))
    tracks = []
    for track in p.tracks:
        if track.id not in scope:
            tracks.append(track)
            continue
        clips: list[Clip] = []
        for c in track.clips:
            if c.end <= start or c.start >= end:
                clips.append(c)
                continue
            if c.start < start:
                clips.append(_cut(c, start, "")[0])
            if c.end > end:
                clips.append(_cut(c, end, c.id if c.start >= start else new_id("c"))[1])
        tracks.append(replace(track, clips=_sorted(clips)))
    return replace(p, tracks=tuple(tracks))


def cut_range(p: Project, start: int, end: int, track_ids=None) -> Project:
    """Ripple-delete ``[start, end)`` on the tracks (``None``: all tracks)."""
    start, end = int(start), int(end)
    if end <= start:
        raise EditError("error.edit.empty_range")
    return ripple_delete(p, start, end, _range_tracks(p, track_ids))


def nudge_clips(p: Project, clip_ids, delta: int, overwrite: bool = True) -> Project:
    """``shift_clips`` that takes the members of the clips' explicit groups along
    (never their sync partners: WP83). Clips they land on are overwritten (no layers)."""
    nudged = shift_clips(p, edit_scope.expand_clips(p, list(clip_ids)), delta)
    return _overwrite_under(p, nudged) if overwrite else nudged


def move_clips_to_track(p: Project, clip_ids, direction: int, delta: int = 0,
                        overwrite: bool = True) -> Project:
    """Drag a clip body: ``nudge_clips`` by ``delta`` frames, and the clips ``direction``
    tracks down (negative: up), in one edit. ``direction`` is clamped so that no clip
    leaves the tracks (the selection, with its explicit group, keeps its shape). Sync
    partners are not moved."""
    chosen = edit_scope.expand_clips(p, list(clip_ids))
    if not chosen:
        raise EditError("error.edit.no_selection")
    index = {t.id: i for i, t in enumerate(p.tracks)}
    rows = [index[_find_clip(p, cid)[1].id] for cid in chosen]
    direction = max(-min(rows), min(len(p.tracks) - 1 - max(rows), int(direction)))
    moved = nudge_clips(p, chosen, int(delta), overwrite=False)
    if direction != 0:
        for cid, row in zip(chosen, rows, strict=True):
            target = p.tracks[row + direction].id
            moved = move_clip(moved, cid, moved.clip(cid).start, target)
    return _overwrite_under(p, moved) if overwrite else moved


def _overwrite_under(before: Project, moved: Project,
                     only: set[str] | None = None) -> Project:
    """Clips on a track never overlap (there are no layers): where a moved clip now lies
    on others, those are trimmed back, split around it, or removed when it covers them
    whole. The audio under a trimmed edge stays put, so nothing is lost; one edit.
    ``only``: the clips that count as moved (an edge drag moves no start)."""
    start_of = {c.id: (t.id, c.start) for t in before.tracks for c in t.clips}
    moved_ids = set(only) if only is not None else {
        c.id for t in moved.tracks for c in t.clips
        if start_of.get(c.id) != (t.id, c.start)}
    for cid in sorted(moved_ids):
        mclip, mtrack = _find_clip(moved, cid)
        lo, hi = mclip.start, mclip.end
        for other in [c for c in mtrack.clips if c.id != cid and c.id not in moved_ids]:
            if other.end <= lo or other.start >= hi:
                continue
            if lo <= other.start and hi >= other.end:
                moved = delete_clip(moved, other.id)
            elif lo <= other.start:  # its front is covered
                moved = trim_clip(moved, other.id, start=hi)
            elif hi >= other.end:  # its end is covered
                moved = trim_clip(moved, other.id, end=lo)
            else:  # strictly inside: split, then trim the right piece
                right_id = new_id("c")
                moved = split_clip(moved, other.id, lo, new_id=right_id)
                moved = trim_clip(moved, right_id, start=hi)
    return moved


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


def synced_start(p: Project, clip: Clip) -> int | None:
    """Where ``clip`` belongs on the timeline to be in sync with its group, or
    None when it has no reference (no group, or it is the main media's own piece).

    The reference is the main media's piece that plays the same stretch of the
    recording, so cuts made in the main clip are followed. Both ``resync`` and
    the drift display (``sync_state``) read it, so they cannot disagree.
    """
    group = p.sync_group(clip.media)
    if group is None or clip.media == group.main:
        return None
    refs = [r for t in p.tracks for r in t.clips if r.media == group.main]
    if not refs:
        return None
    rec = _recorded(p, clip)

    def score(r: Clip) -> tuple[int, int]:
        r_rec = _recorded(p, r)
        overlap = min(r_rec + r.length, rec + clip.length) - max(r_rec, rec)
        return (overlap if overlap > 0 else overlap * 2, -abs(r.start - clip.start))

    ref = max(refs, key=score)
    return max(0, ref.start + (rec - _recorded(p, ref)))


def resync(p: Project, clip_ids) -> Project:
    """Move each clip back into sync with the main clip's piece it belongs with.

    Clips without a group, and the main media's own pieces, stay where they are,
    and so do clips declared free from sync (``set_free``): resync never undoes
    something the user said was deliberate.
    """
    for clip_id in clip_ids:
        c, _ = _find_clip(p, clip_id)
        if c.free:
            continue
        start = synced_start(p, c)
        if start is not None:
            p = _replace_clip(p, replace(c, start=start))
    return p


def send_home(p: Project, clip_ids) -> Project:
    """Put clips back on the track they were dragged away from, at the same time
    position. Clips that never left (or whose home track is gone) stay."""
    tracks = {t.id for t in p.tracks}
    before = p
    for clip_id in clip_ids:
        c, _ = _find_clip(p, clip_id)
        if c.home is not None and c.home in tracks:
            p = move_clip(p, clip_id, c.start, c.home)
    return _overwrite_under(before, p) if p != before else p


def set_sync_anchor(p: Project, clip_id: str) -> Project:
    """Make this clip's media the main of its sync group (the anchor that resync
    and the drift badge measure against) without moving anything: every member's
    origin is re-expressed relative to the new main, so the differences between
    them, and so every clip's sync state, stay as they are."""
    clip, _ = _find_clip(p, clip_id)
    group = p.sync_group(clip.media)
    if group is None:
        raise EditError("error.edit.no_sync_group")
    if group.main == clip.media:
        return p
    shift = dict(group.members).get(clip.media, 0)
    members = tuple(sorted(
        (m, o - shift) for m, o in {**dict(group.members), group.main: 0}.items()))
    new = replace(group, main=clip.media, members=members)
    return replace(p, sync_groups=tuple(new if g.id == group.id else g
                                        for g in p.sync_groups))


def set_free(p: Project, clip_ids, free: bool | None = None) -> Project:
    """Declare clips free from sync (or link them again). ``free=None`` toggles
    the selection: if any clip is linked they all become free, else all link."""
    ids = list(clip_ids)
    if not ids:
        raise EditError("error.edit.no_selection")
    clips = [_find_clip(p, cid)[0] for cid in ids]
    want = (not all(c.free for c in clips)) if free is None else bool(free)
    for c in clips:
        if c.free != want:
            p = _replace_clip(p, replace(c, free=want))
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
    # Markers sit on the timeline, not on a track: they move only when every
    # track is cut, otherwise the audio they point at has not moved.
    moved = (markersm.ripple(p.markers, start, end)
             if scope >= {t.id for t in p.tracks} else p.markers)
    # A placeholder is a range of one track (WP43): it follows its own track.
    return replace(p, tracks=tuple(tracks), markers=moved,
                   placeholders=placeholdersm.ripple(p.placeholders, scope, start, end))


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


# -- dragging a clip edge (WP6) ---------------------------------------------------


def _edge(edge: str) -> str:
    if edge not in ("start", "end"):
        raise EditError("error.edit.bad_edge", edge=edge)
    return edge


def _source_span(p: Project, clip: Clip) -> tuple[int, int]:
    """The timeline frames ``clip`` can be stretched to without needing source
    material before the media's first frame or after its last."""
    media = p.media_item(clip.media)
    origin = clip.start - clip.offset  # where the media's first frame would sit
    return max(origin, 0), origin + media.frames


def _touching(track: Track, clip: Clip, edge: str) -> Clip | None:
    """The clip on the same track that meets ``clip`` exactly at ``edge``."""
    for other in track.clips:
        if other.id == clip.id:
            continue
        if edge == "end" and other.start == clip.end:
            return other
        if edge == "start" and other.end == clip.start:
            return other
    return None


def roll_trim(p: Project, clip_id: str, edge: str, frame: int,
              overwrite: bool = True) -> Project:
    """Drag one edge of a clip to ``frame``; nothing else on the timeline moves.

    ``overwrite`` (the default, as a clip move does): an edge dragged outwards
    covers its neighbours like a moved clip does (no layers): what it covers is
    trimmed or, when covered whole, removed, across several clips. Only the
    clip's own media limits the drag. ``overwrite=False`` (Alt) stops at the
    neighbour as below. Shrinking an edge is the same either way.

    If a clip on the same track touches that edge, the cut point between the
    two moves: one grows, the other shrinks, each source offset keeping the
    audio where it was. With nothing touching it is a plain trim into (or out
    of) the gap. ``frame`` is clamped so no clip drops below one frame and no
    clip needs source beyond its media.
    """
    edge = _edge(edge)
    clip, track = _find_clip(p, clip_id)
    if overwrite:
        own_low, own_high = _source_span(p, clip)
        if edge == "end":
            target = max(clip.start + 1, min(own_high, int(frame)))
            if target > clip.end:
                p = trim_clip(p, clip_id, end=target)
                return _overwrite_under(p, p, {clip_id})
        else:
            target = max(own_low, min(clip.end - 1, int(frame)))
            if target < clip.start:
                p = trim_clip(p, clip_id, start=target)
                return _overwrite_under(p, p, {clip_id})
    other = _touching(track, clip, edge)
    low, high = _source_span(p, clip)
    if edge == "end":
        low = clip.start + 1
    else:
        high = clip.end - 1
    if other is not None:
        o_low, o_high = _source_span(p, other)
        if edge == "end":
            # The neighbour's start moves: it keeps 1 frame, or needs its source.
            low, high = max(low, o_low), min(high, other.end - 1)
        else:
            low, high = max(low, other.start + 1), min(high, o_high)
    elif edge == "end":  # a gap: stop at the next clip, as the drag does
        high = min([high, *(c.start for c in track.clips
                            if c.id != clip_id and c.start >= clip.end)])
    else:
        low = max([low, *(c.end for c in track.clips
                          if c.id != clip_id and c.end <= clip.start)])
    if low > high:
        raise EditError("error.edit.trim_empty")
    frame = max(low, min(high, int(frame)))
    if edge == "end":
        p = trim_clip(p, clip_id, end=frame)
        return p if other is None else trim_clip(p, other.id, start=frame)
    p = trim_clip(p, clip_id, start=frame)
    return p if other is None else trim_clip(p, other.id, end=frame)


def ripple_trim(p: Project, clip_id: str, edge: str, frame: int,
                extend_partners: bool = False,
                track_ids: list[str] | None = None) -> Project:
    """Drag one edge of a clip to ``frame``; everything after the clip, on every
    track, moves by the change in its length, so the tracks stay in sync.

    The clip keeps its start on the timeline. Dragging its start edge to
    ``frame`` takes (or gives back) the source between its start and ``frame``,
    and what follows moves by that much. A shorter clip closes the gap as a
    ripple delete does (the stretch it lost goes from every track); a longer
    one opens a gap of the same length on every track, with markers,
    automation and gates following.

    ``track_ids``: the tracks that shift (None: all, as above).

    ``extend_partners`` (a longer end edge): the clips on the other tracks that end
    at the same splice (within 50 ms) grow by the same amount instead of leaving a
    gap, as far as their recordings reach: the material cut from every track at
    once comes back on every track at once.
    """
    edge = _edge(edge)
    clip, _ = _find_clip(p, clip_id)
    if edge == "end":
        new_end = max(clip.start + 1, min(_source_span(p, clip)[1], int(frame)))
        take = 0
    else:
        # frame - start is the source taken from the head; negative gives it back.
        frame = max(clip.start - clip.offset, min(clip.end - 1, int(frame)))
        take = frame - clip.start
        new_end = clip.end - take
    delta = new_end - clip.end
    if delta == 0:
        return p
    if delta > 0:
        from .paste_apply import _open_gap  # noqa: PLC0415 - paste_apply imports ops
        scope = {t.id for t in p.tracks} if track_ids is None else set(track_ids)
        for track in p.tracks:
            if track.id in scope:
                p = _open_gap(p, track.id, clip.end, delta)
        if scope >= {t.id for t in p.tracks}:  # markers move only when every track does
            p = replace(p, markers=markersm.open_gap(p.markers, clip.end, delta))
    length = new_end - clip.start
    changed = replace(
        clip, offset=clip.offset + take, length=length,
        fade_in=min(clip.fade_in, length), fade_out=min(clip.fade_out, length),
        xfade_in=clip.xfade_in if take == 0 else 0,
        xfade_out=clip.xfade_out if delta == 0 else 0)
    p = _replace_clip(p, changed)
    if delta < 0:
        p = ripple_delete(p, new_end, clip.end, track_ids)
    elif extend_partners and edge == "end":
        near = p.rate // 20
        for track in p.tracks:
            for other in track.clips:
                if other.id != clip_id and abs(other.end - clip.end) <= near:
                    p = trim_clip(p, other.id, end=other.end + delta)
    return p


# -- markers, regions, chapters (WP19h) -----------------------------------------


def _find_marker(p: Project, marker_id: str) -> Marker:
    for m in p.markers:
        if m.id == marker_id:
            return m
    raise EditError("error.marker.missing", marker_id=marker_id)


def _put_marker(p: Project, marker: Marker) -> Project:
    others = tuple(m for m in p.markers if m.id != marker.id)
    return replace(p, markers=markersm.ordered((*others, marker)))


def _checked(marker: Marker) -> Marker:
    if marker.kind not in markersm.KINDS:
        raise EditError("error.marker.bad_kind", kind=marker.kind)
    if marker.start < 0 or (marker.kind == "region") != (marker.end is not None) or (
            marker.end is not None and marker.end <= marker.start):
        raise EditError("error.marker.bad_range")
    return marker


def add_marker(p: Project, marker_id: str | None, name: str, start: int,
               end: int | None = None, kind: str = "marker") -> Project:
    """A marker, chapter (``end`` None) or region (``end`` after ``start``)."""
    marker_id = marker_id or new_id("k")
    if any(m.id == marker_id for m in p.markers):
        raise EditError("error.marker.exists", marker_id=marker_id)
    return _put_marker(p, _checked(Marker(
        id=marker_id, name=str(name).strip(), start=int(start),
        end=None if end is None else int(end), kind=kind)))


def rename_marker(p: Project, marker_id: str, name: str) -> Project:
    return _put_marker(p, replace(_find_marker(p, marker_id), name=str(name).strip()))


def move_marker(p: Project, marker_id: str, start: int) -> Project:
    """Move to ``start``; a region keeps its length."""
    m = _find_marker(p, marker_id)
    start = int(start)
    end = None if m.end is None else start + (m.end - m.start)
    return _put_marker(p, _checked(replace(m, start=start, end=end)))


def set_region_end(p: Project, marker_id: str, end: int) -> Project:
    m = _find_marker(p, marker_id)
    if m.kind != "region":
        raise EditError("error.marker.not_region", marker_id=marker_id)
    return _put_marker(p, _checked(replace(m, end=int(end))))


def set_marker_kind(p: Project, marker_id: str, kind: str,
                    end: int | None = None) -> Project:
    """Change the kind. To a region it needs an ``end`` (or already has one);
    from a region the end is dropped."""
    m = _find_marker(p, marker_id)
    end = (m.end if end is None else int(end)) if kind == "region" else None
    return _put_marker(p, _checked(replace(m, kind=kind, end=end)))


def delete_marker(p: Project, marker_id: str) -> Project:
    _find_marker(p, marker_id)
    return replace(p, markers=tuple(m for m in p.markers if m.id != marker_id))


# -- narration placeholders (WP43) ----------------------------------------------


def _find_placeholder(p: Project, placeholder_id: str) -> Placeholder:
    for h in p.placeholders:
        if h.id == placeholder_id:
            return h
    raise EditError("error.placeholder.missing", placeholder_id=placeholder_id)


def _put_placeholder(p: Project, h: Placeholder) -> Project:
    others = tuple(x for x in p.placeholders if x.id != h.id)
    return replace(p, placeholders=placeholdersm.ordered((*others, h)))


def _clean_text(text) -> str:
    """Script text needs at least one word, or there is nothing to estimate."""
    text = str(text).strip()
    if narration.count_words(text) == 0:
        raise EditError("error.placeholder.empty_text")
    return text


def _clean_length(length) -> int:
    length = int(length)
    if length <= 0:
        raise EditError("error.placeholder.bad_length")
    return length


def add_placeholder(p: Project, track_id: str, start: int, text: str,
                    length: int | None = None, placeholder_id: str | None = None,
                    language: str = "") -> Project:
    """Script text at ``start`` on a track. Without ``length`` it is estimated
    from the text (``narration.estimate_frames``) and stays an estimate."""
    _find_track(p, track_id)
    text = _clean_text(text)
    placeholder_id = placeholder_id or new_id("h")
    if any(h.id == placeholder_id for h in p.placeholders):
        raise EditError("error.placeholder.exists", placeholder_id=placeholder_id)
    if int(start) < 0:
        raise EditError("error.placeholder.bad_start")
    estimated = length is None
    frames = (narration.estimate_frames(text, p.rate) if estimated
              else _clean_length(length))
    return _put_placeholder(p, Placeholder(
        id=placeholder_id, track=track_id, start=int(start), length=frames, text=text,
        estimated=estimated, language=str(language)))


def edit_placeholder_text(p: Project, placeholder_id: str, text: str) -> Project:
    """New text; the length follows it while it is still an estimate."""
    h = _find_placeholder(p, placeholder_id)
    text = _clean_text(text)
    if h.estimated:
        h = replace(h, length=narration.estimate_frames(text, p.rate))
    return _put_placeholder(p, replace(h, text=text))


def set_placeholder_length(p: Project, placeholder_id: str, length: int) -> Project:
    """A hand-set length: no longer an estimate, so editing the text keeps it."""
    h = _find_placeholder(p, placeholder_id)
    return _put_placeholder(p, replace(h, length=_clean_length(length), estimated=False))


def move_placeholder(p: Project, placeholder_id: str, start: int,
                     track_id: str | None = None) -> Project:
    h = _find_placeholder(p, placeholder_id)
    if int(start) < 0:
        raise EditError("error.placeholder.bad_start")
    if track_id is not None:
        _find_track(p, track_id)
    return _put_placeholder(p, replace(h, start=int(start), track=track_id or h.track))


def delete_placeholder(p: Project, placeholder_id: str) -> Project:
    _find_placeholder(p, placeholder_id)
    return replace(p, placeholders=tuple(h for h in p.placeholders
                                         if h.id != placeholder_id))


def replace_placeholder(p: Project, placeholder_id: str, media_id: str,
                        offset: int = 0, track_ids=None) -> Project:
    """Record it: the placeholder becomes a clip of ``media_id`` (from
    ``offset``) at the same start on the same track, and the later material
    moves by the take's length minus the placeholder's, on ``track_ids`` (``None``:
    all tracks, ``edit_scope.range_tracks``). One pure step, so one undo.

    A longer take opens a gap where the placeholder ended, a shorter one
    ripple-deletes the leftover; anything on the track inside that leftover
    goes with it, as with any ripple delete.
    """
    # Imported here: paste_apply imports ops.
    from .paste_apply import _open_gap  # noqa: PLC0415 - paste_apply imports ops

    h = _find_placeholder(p, placeholder_id)
    try:
        media = p.media_item(media_id)
    except KeyError:
        raise EditError("error.edit.no_media", media_id=media_id) from None
    offset = int(offset)
    take = media.frames - offset
    if offset < 0 or take <= 0:
        raise EditError("error.edit.clip_outside_media")
    p = delete_placeholder(p, placeholder_id)
    delta = take - h.length
    if delta > 0:
        scope = _range_tracks(p, track_ids)
        for track in p.tracks:
            if track.id in scope:
                p = _open_gap(p, track.id, h.end, delta)
        if set(scope) >= {t.id for t in p.tracks}:
            p = replace(p, markers=markersm.open_gap(p.markers, h.end, delta))
    elif delta < 0:
        cut_from, cut_to = h.start + take, h.end
        scope = _range_tracks(p, track_ids)
        p = ripple_delete(p, cut_from, cut_to, scope)
    return add_clip(p, h.track, media_id, h.start, offset, take)


# -- dispatch ----------------------------------------------------------------

OPS = {
    f.__name__: f
    for f in (
        add_track, delete_track, delete_empty_tracks, set_track, solo, move_track,
        set_track_automation,
        add_bus, set_bus, delete_bus, set_master, reset_gains,
        add_clip, delete_clip, move_clip, trim_clip, split_clip, set_clip,
        set_fade_at, set_clip_envelope, ripple_delete, mute_ranges,
        set_gate, add_gate_range, remove_gate_range,
        add_marker, rename_marker, move_marker, set_region_end, delete_marker,
        set_marker_kind,
        add_placeholder, edit_placeholder_text, set_placeholder_length,
        move_placeholder, delete_placeholder, replace_placeholder,
        shift_clips, set_clips, delete_clips, mark_in_sync, resync, set_free,
        send_home, set_sync_anchor,
        split_clips, mute_range, cut_range, nudge_clips, move_clips_to_track,
        trim_clips, adjust_clip_gain,
        restore_cuts, roll_trim, ripple_trim, group_clips, ungroup_clips, merge_clips,
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
