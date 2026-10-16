"""The project: plain immutable data.

Every position is an integer frame at the project rate. Seconds as floats
drift under repeated split/trim/ripple; frames do not.

Each edit returns a new ``Project`` (see ``ops``); the history stores whole
states, so nothing here needs to know how to undo itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace

Point = tuple[int, float]  # (frame, dB)


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


@dataclass(frozen=True)
class Bus:
    id: str
    name: str
    gain_db: float = 0.0
    pan: float = 0.0
    mute: bool = False


@dataclass(frozen=True)
class Project:
    rate: int = 48000
    media: tuple[Media, ...] = ()
    tracks: tuple[Track, ...] = ()
    buses: tuple[Bus, ...] = ()
    master_gain_db: float = 0.0
    # media id -> transcript revision id (``history.History.transcript``).
    # Transcripts live outside the state so every undo step stays small.
    transcripts: tuple[tuple[str, int], ...] = field(default=())
    # (group id, main clip's media id)
    sync_groups: tuple[tuple[str, str], ...] = ()

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

    def transcript_rev(self, media_id: str) -> int | None:
        return dict(self.transcripts).get(media_id)

    @property
    def length(self) -> int:
        return max((c.end for t in self.tracks for c in t.clips), default=0)

    # -- serialisation ----------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        def points(raw) -> tuple[Point, ...]:
            return tuple((int(f), float(db)) for f, db in raw)

        tracks = tuple(
            replace(
                Track(**{k: v for k, v in t.items() if k not in ("clips", "automation")}),
                clips=tuple(
                    Clip(**{**c, "envelope": points(c["envelope"])}) for c in t["clips"]
                ),
                automation=points(t["automation"]),
            )
            for t in d["tracks"]
        )
        return cls(
            rate=d["rate"],
            media=tuple(Media(**m) for m in d["media"]),
            tracks=tracks,
            buses=tuple(Bus(**b) for b in d["buses"]),
            master_gain_db=d["master_gain_db"],
            transcripts=tuple((m, int(r)) for m, r in d["transcripts"]),
            sync_groups=tuple((g, m) for g, m in d.get("sync_groups", ())),
        )

    @classmethod
    def from_json(cls, text: str) -> Project:
        return cls.from_dict(json.loads(text))
