"""The project: plain immutable data.

Every position is an integer frame at the project rate. Seconds as floats
drift under repeated split/trim/ripple; frames do not.

Each edit returns a new ``Project`` (see ``ops``); the history stores whole
states, so nothing here needs to know how to undo itself.

**Never destroy what you cannot read** (docs/FORMAT.md). Every class has
``extra``: the keys a newer kuulas (or a Hindenburg import) wrote that this
version does not model. ``from_dict`` puts them there and ``to_dict`` writes
them back beside the known keys, so a save by this version loses nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields

Point = tuple[int, float]  # (frame, dB)


def _known(cls) -> set[str]:
    return {f.name for f in fields(cls)} - {"extra"}


def _split(cls, d: dict) -> tuple[dict, dict]:
    """``d`` as (keys ``cls`` knows, the rest)."""
    known = _known(cls)
    return ({k: v for k, v in d.items() if k in known},
            {k: v for k, v in d.items() if k not in known})


def _out(obj, **override) -> dict:
    """The known fields (``override`` replacing some), then the extras under them.

    A known key always wins over an extra of the same name.
    """
    d = {f.name: getattr(obj, f.name) for f in fields(obj) if f.name != "extra"}
    d.update(override)
    return {**obj.extra, **d}


def _points(raw) -> tuple[Point, ...]:
    return tuple((int(f), float(db)) for f, db in raw)


@dataclass(frozen=True)
class Media:
    """An imported source file, decoded to the project rate (``media.Store``)."""

    id: str
    name: str
    channels: int
    frames: int
    sha256: str = ""
    # Recording start on the recorder's clock (BWF TimeReference), in flicks
    # (``clock``), so it never rounds; None when the file carries none.
    # ``ops.mark_in_sync(basis="files")``.
    time_ref_flicks: int | None = None
    # A WP20 excerpt: a copy of part of another media. Its frame 0 is the
    # original's ``excerpt_start_flicks``, so it shares the original's sync.
    excerpt_of: str | None = None
    excerpt_start_flicks: int = 0
    # Whose voice is on this file, for a single-person mic (WP41). Material:
    # filled in from the material root by ``History.state``, not a database column.
    person: str = ""
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self)

    @classmethod
    def from_dict(cls, d: dict) -> Media:
        known, extra = _split(cls, d)
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Clip:
    """A window onto a media file, placed on a track.

    ``envelope`` is in *source* frames, so the automation stays attached to
    the audio it was drawn on when the clip is trimmed, split or moved.
    """

    id: str
    media: str
    start: int  # timeline frame
    offset: int  # source frame at ``start``
    length: int
    gain_db: float = 0.0
    pan: float = 0.0  # -1 (left) .. 1 (right)
    fade_in: int = 0
    fade_out: int = 0
    muted: bool = False
    name: str = ""
    envelope: tuple[Point, ...] = ()
    # Crossfades at a join of non-adjacent audio, centred on the edge: the
    # clip plays ``xfade/2`` frames of its source beyond the edge, so the
    # timeline does not move. Even lengths; zero at a plain split.
    xfade_in: int = 0
    xfade_out: int = 0
    # Sync is per media, not per clip (``Project.sync_groups``): every piece
    # cut from a file shares its clock, so subclips need no fields of their own.
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        d = _out(self, envelope=[list(pt) for pt in self.envelope])
        if not self.name:
            del d["name"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Clip:
        known, extra = _split(cls, d)
        known["envelope"] = _points(known.get("envelope", ()))
        return cls(**known, extra=extra)

    @property
    def end(self) -> int:
        return self.start + self.length

    @property
    def heard_start(self) -> int:
        return self.start - self.xfade_in // 2

    @property
    def heard_end(self) -> int:
        return self.end + self.xfade_out // 2


@dataclass(frozen=True)
class Track:
    """``automation`` is in timeline frames: it is where the automixer writes
    its ducking, as editable points rather than baked-in samples."""

    id: str
    name: str
    kind: str = "speech"  # "speech" | "speech-mix" | "music"
    speaker: str = ""
    bus: str | None = None
    gain_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    clips: tuple[Clip, ...] = ()
    automation: tuple[Point, ...] = ()
    # Auto-Silence's result (WP44): closed ranges ``(start, end)`` in timeline
    # frames, sorted, non-overlapping, not touching (``gate.normalise``).
    # Where it is closed the track is silent, whatever the clips there say;
    # the mixer derives the 30 ms edge ramps, none are stored. Part of the
    # edit state, so history keeps it.
    gate: tuple[tuple[int, int], ...] = ()
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        d = _out(self, clips=[c.to_dict() for c in self.clips],
                 automation=[list(pt) for pt in self.automation],
                 gate=[list(r) for r in self.gate])
        if not self.gate:
            # Absent means empty: a track that never had a gate keeps its
            # bytes (and its state hash) from before the field existed.
            del d["gate"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Track:
        known, extra = _split(cls, d)
        known["clips"] = tuple(Clip.from_dict(c) for c in known.get("clips", ()))
        known["automation"] = _points(known.get("automation", ()))
        known["gate"] = tuple((int(a), int(b)) for a, b in known.get("gate", ()))
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Bus:
    id: str
    name: str
    gain_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self)

    @classmethod
    def from_dict(cls, d: dict) -> Bus:
        known, extra = _split(cls, d)
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class SyncGroup:
    """Recordings that ran on one clock (``ops.mark_in_sync``).

    ``members``: ``(media id, origin)`` pairs, the origin being where that
    media's frame 0 sits on the group's recording clock, relative to the
    ``main`` media's frame 0, in flicks. Material: shared by every edit.
    """

    id: str
    main: str
    members: tuple[tuple[str, int], ...] = ()
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self, members=dict(self.members))

    @classmethod
    def from_dict(cls, d: dict) -> SyncGroup:
        known, extra = _split(cls, d)
        members = dict(known.get("members", {}))
        known["members"] = tuple(sorted((m, int(o)) for m, o in members.items()))
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Marker:
    """A named point or range on the timeline (WP19h), in project frames.

    ``kind``: ``"marker"`` (a point), ``"chapter"`` (a point that goes in the
    chapter list) or ``"region"`` (a range ``[start, end)``; only a region has
    an ``end``). Edit state: undoable, and it moves with ripple edits.
    """

    id: str
    name: str
    start: int
    end: int | None = None
    kind: str = "marker"
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        d = _out(self)
        if self.end is None:
            del d["end"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Marker:
        known, extra = _split(cls, d)
        known["start"] = int(known["start"])
        if known.get("end") is not None:
            known["end"] = int(known["end"])
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Placeholder:
    """Narration script that is not recorded yet (WP43): ``text`` standing for
    ``length`` frames from ``start`` on ``track``, in project frames.

    It plays silence and is no clip (a clip without media would break every
    place that reads ``Clip.media``). ``estimated`` says ``length`` still comes
    from the text (``narration.estimate_frames``); a hand-set length clears it.
    ``language`` is a language tag, empty for the project's.
    """

    id: str
    track: str
    start: int
    length: int
    text: str
    estimated: bool = True
    language: str = ""
    extra: dict = field(default_factory=dict, hash=False)

    @property
    def end(self) -> int:
        return self.start + self.length

    def to_dict(self) -> dict:
        d = _out(self)
        if not self.language:
            del d["language"]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Placeholder:
        known, extra = _split(cls, d)
        known["start"] = int(known["start"])
        known["length"] = int(known["length"])
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Project:
    rate: int = 48000
    media: tuple[Media, ...] = ()
    tracks: tuple[Track, ...] = ()
    buses: tuple[Bus, ...] = ()
    master_gain_db: float = 0.0
    # Material, shared by every edit (``History`` keeps it apart): sync groups
    # here; transcripts in ``History.transcripts``.
    sync_groups: tuple[SyncGroup, ...] = ()
    # Edit state (WP19h): sorted by start. Absent from the JSON when empty, so
    # a project that never had one keeps its bytes and its state hash.
    markers: tuple[Marker, ...] = ()
    # Edit state (WP43), sorted by start; absent from the JSON when empty.
    placeholders: tuple[Placeholder, ...] = ()
    extra: dict = field(default_factory=dict, hash=False)

    # -- lookups ----------------------------------------------------------

    def track(self, track_id: str) -> Track:
        for t in self.tracks:
            if t.id == track_id:
                return t
        raise KeyError(track_id)

    def bus(self, bus_id: str) -> Bus:
        for b in self.buses:
            if b.id == bus_id:
                return b
        raise KeyError(bus_id)

    def media_item(self, media_id: str) -> Media:
        for m in self.media:
            if m.id == media_id:
                return m
        raise KeyError(media_id)

    def clip(self, clip_id: str) -> Clip:
        return self.clip_and_track(clip_id)[0]

    def clip_and_track(self, clip_id: str) -> tuple[Clip, Track]:
        for t in self.tracks:
            for c in t.clips:
                if c.id == clip_id:
                    return c, t
        raise KeyError(clip_id)

    def sync_member(self, media_id: str) -> tuple[SyncGroup, int] | None:
        """The group ``media_id`` belongs to and its origin in flicks.

        An excerpt that was never marked itself belongs where its original
        does, at the original's origin plus where the excerpt starts.
        """
        for g in self.sync_groups:
            for member, origin in g.members:
                if member == media_id:
                    return g, origin
        try:
            media = self.media_item(media_id)
        except KeyError:
            return None
        if media.excerpt_of and media.excerpt_of != media_id:
            found = self.sync_member(media.excerpt_of)
            if found is not None:
                return found[0], found[1] + media.excerpt_start_flicks
        return None

    def sync_group(self, media_id: str) -> SyncGroup | None:
        found = self.sync_member(media_id)
        return None if found is None else found[0]

    @property
    def length(self) -> int:
        return max(
            (c.end for t in self.tracks for c in t.clips if not c.muted), default=0
        )

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> dict:
        d = _out(self, media=[m.to_dict() for m in self.media],
                 tracks=[t.to_dict() for t in self.tracks],
                 buses=[b.to_dict() for b in self.buses],
                 sync_groups=[g.to_dict() for g in self.sync_groups],
                 markers=[m.to_dict() for m in self.markers],
                 placeholders=[h.to_dict() for h in self.placeholders])
        if not self.markers:
            del d["markers"]
        if not self.placeholders:
            del d["placeholders"]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        known, extra = _split(cls, d)
        known["media"] = tuple(Media.from_dict(m) for m in known.get("media", ()))
        known["tracks"] = tuple(Track.from_dict(t) for t in known.get("tracks", ()))
        known["buses"] = tuple(Bus.from_dict(b) for b in known.get("buses", ()))
        known["sync_groups"] = tuple(SyncGroup.from_dict(g)
                                     for g in known.get("sync_groups", ()))
        known["markers"] = tuple(Marker.from_dict(m) for m in known.get("markers", ()))
        known["placeholders"] = tuple(Placeholder.from_dict(h)
                                      for h in known.get("placeholders", ()))
        return cls(**known, extra=extra)

    @classmethod
    def from_json(cls, text: str) -> Project:
        return cls.from_dict(json.loads(text))
