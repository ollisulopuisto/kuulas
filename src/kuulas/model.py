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
    # Recording start on the recorder's clock (BWF TimeReference), in project
    # frames; 0 when the file carries none. ``ops.mark_in_sync(basis="files")``.
    time_ref: int = 0
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
    envelope: tuple[Point, ...] = ()
    # Crossfades at a join of non-adjacent audio, centred on the edge: the
    # clip plays ``xfade/2`` frames of its source beyond the edge, so the
    # timeline does not move. Even lengths; zero at a plain split.
    xfade_in: int = 0
    xfade_out: int = 0
    # Sync group (``ops.mark_in_sync``) and this clip's recording-time origin
    # relative to the group's main clip. Splits inherit both, so every
    # subclip can be resynced on its own.
    sync: str | None = None
    sync_origin: int = 0
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self, envelope=[list(pt) for pt in self.envelope])

    @classmethod
    def from_dict(cls, d: dict) -> Clip:
        known, extra = _split(cls, d)
        known["envelope"] = _points(known.get("envelope", ()))
        return cls(**known, extra=extra)

    @property
    def recorded(self) -> int:
        """Where this clip's first frame sits on the group's recording clock."""
        return self.offset + self.sync_origin

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
    kind: str = "speech"  # "speech" | "music"
    bus: str | None = None
    gain_db: float = 0.0
    pan: float = 0.0
    mute: bool = False
    solo: bool = False
    clips: tuple[Clip, ...] = ()
    automation: tuple[Point, ...] = ()
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self, clips=[c.to_dict() for c in self.clips],
                    automation=[list(pt) for pt in self.automation])

    @classmethod
    def from_dict(cls, d: dict) -> Track:
        known, extra = _split(cls, d)
        known["clips"] = tuple(Clip.from_dict(c) for c in known.get("clips", ()))
        known["automation"] = _points(known.get("automation", ()))
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
class Project:
    rate: int = 48000
    media: tuple[Media, ...] = ()
    tracks: tuple[Track, ...] = ()
    buses: tuple[Bus, ...] = ()
    master_gain_db: float = 0.0
    # (group id, main clip's media id)
    sync_groups: tuple[tuple[str, str], ...] = ()
    extra: dict = field(default_factory=dict, hash=False)
    # Transcripts are material, shared by every edit: ``History.transcripts``.

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

    @property
    def length(self) -> int:
        return max((c.end for t in self.tracks for c in t.clips), default=0)

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> dict:
        return _out(self, media=[m.to_dict() for m in self.media],
                    tracks=[t.to_dict() for t in self.tracks],
                    buses=[b.to_dict() for b in self.buses],
                    sync_groups=[list(g) for g in self.sync_groups])

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        known, extra = _split(cls, d)
        known["media"] = tuple(Media.from_dict(m) for m in known.get("media", ()))
        known["tracks"] = tuple(Track.from_dict(t) for t in known.get("tracks", ()))
        known["buses"] = tuple(Bus.from_dict(b) for b in known.get("buses", ()))
        known["sync_groups"] = tuple((g, m) for g, m in known.get("sync_groups", ()))
        return cls(**known, extra=extra)

    @classmethod
    def from_json(cls, text: str) -> Project:
        return cls.from_dict(json.loads(text))
