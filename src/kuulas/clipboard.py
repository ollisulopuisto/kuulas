"""Clipboard entries and their history (WP46, first part).

A clipboard entry is a snapshot of the copied clips as references — the
recording's SHA-256, the source window, gain, pan, fades and envelope, and
the layout — never audio, so a copy costs nothing whatever it came from.
Entries live in a history list with pinning, and survive restarts as JSON
(WP20's text clipboard format), so they can be pasted into another open
project.

This is the logic only: no audio, no file I/O, no session wiring. Where a
paste would land is a later module (WP46, second part).
"""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from .model import Clip, Point, Project, Track
from .ops import EditError

_ids = itertools.count()


def _new_id(now: float) -> str:
    """A time-ordered hex id, unique in this process: 12 hex digits of UTC
    milliseconds, then 8 of a per-process counter, so two entries made at
    one injected ``now`` never share an id and ids sort as they were made."""
    return f"{int(now * 1000):012x}{next(_ids):08x}"


@dataclass(frozen=True)
class ClipRef:
    """One copied clip: a plain window onto a recording, placed by layout.

    ``media_sha256`` identifies the recording (content identity, never a
    file name); ``offset`` and ``length`` are source frames; ``envelope``
    is in source frames too, so the automation stays attached to the same
    audio however the window was trimmed. ``rel_start`` is the clip's
    timeline start relative to the earliest copied clip, and
    ``track_slot`` numbers the source tracks, so a paste can rebuild the
    layout and map the tracks onto other tracks without the source project.

    Crossfades are not carried: one belongs to a join on the timeline, and
    a paste makes its own joins (WP20).
    """

    media_sha256: str
    offset: int
    length: int
    gain_db: float = 0.0
    pan: float = 0.0
    fade_in: int = 0
    fade_out: int = 0
    muted: bool = False
    envelope: tuple[Point, ...] = ()
    rel_start: int = 0
    track_slot: int = 0
    # Unknown keys a newer kuulas wrote (docs/FORMAT.md, "Unknown keys").
    extra: dict = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class Entry:
    """One clipboard entry: a snapshot of copied clips, never audio.

    ``span`` is the timeline range the copied clips cover in the source
    project, from the earliest copied clip's start to the latest one's end,
    so ``span[0]`` is where ``rel_start`` 0 sits; it is not the requested
    range when a range copy's edges were silent. ``source_project`` is the
    source project's folder (WP20's clipboard format), empty until the
    session wiring fills it in: the ``Project`` dataclass carries no path.
    """

    id: str
    name: str
    created_utc: float
    refs: tuple[ClipRef, ...] = ()
    span: tuple[int, int] = (0, 0)
    source_project: str = ""
    pinned: bool = False
    # Unknown keys a newer kuulas wrote (docs/FORMAT.md, "Unknown keys").
    extra: dict = field(default_factory=dict, hash=False)


@dataclass(frozen=True)
class _Part:
    """One clip to copy, already trimmed to the copied stretch."""

    track_id: str
    clip: Clip
    start: int  # timeline start of the copied stretch
    offset: int  # source frame at ``start``
    length: int
    fade_in: int  # the clip's own fade, kept only where its own edge is kept
    fade_out: int


def _sha256_of(project: Project, clip: Clip) -> str:
    """The recording's SHA-256 behind a clip."""
    try:
        return project.media_item(clip.media).sha256
    except KeyError:
        raise EditError("error.edit.no_media", media_id=clip.media) from None


def _chosen_tracks(project: Project,
                   track_ids: Iterable[str] | None) -> tuple[Track, ...]:
    """The tracks a range copy reads: every track, or the listed ones."""
    if track_ids is None:
        return project.tracks
    out = []
    for track_id in dict.fromkeys(track_ids):
        try:
            out.append(project.track(track_id))
        except KeyError:
            raise EditError("error.edit.no_track", track_id=track_id) from None
    return tuple(out)


def _entry(project: Project, parts: list[_Part], name: str,
           moment: float) -> Entry:
    """The entry for the trimmed ``parts``: slots, relative layout, span."""
    # Slots follow the project's track order: the same selection gives the
    # same slots however it is listed, and the topmost source track maps to
    # the topmost track on a same-tracks paste.
    touched = {part.track_id for part in parts}
    slots: dict[str, int] = {}
    for track in project.tracks:
        if track.id in touched:
            slots[track.id] = len(slots)
    base = min(part.start for part in parts)
    refs = tuple(sorted(
        (ClipRef(_sha256_of(project, part.clip), part.offset, part.length,
                 gain_db=part.clip.gain_db, pan=part.clip.pan,
                 fade_in=part.fade_in, fade_out=part.fade_out,
                 muted=part.clip.muted, envelope=part.clip.envelope,
                 rel_start=part.start - base, track_slot=slots[part.track_id])
         for part in parts),
        key=lambda ref: (ref.rel_start, ref.track_slot, ref.offset)))
    end = max(part.start + part.length for part in parts)
    # The source tracks' names by slot, so the panel can say where a copy came
    # from without the source project (an unknown key to older readers).
    names = [track.name for track in project.tracks if track.id in touched]
    return Entry(_new_id(moment), name, moment, refs=refs, span=(base, end),
                 extra={"tracks": names})


def make_entry(project: Project, clip_ids: Iterable[str], *, name: str = "",
               now: float | None = None) -> Entry:
    """An entry holding the listed clips, whole and untrimmed.

    The clips keep their relative layout (``rel_start``) and their tracks'
    slots, whatever order ``clip_ids`` is listed in. An empty selection
    raises; so does a clip or a track the project does not have.
    """
    moment = time.time() if now is None else float(now)
    parts = []
    for clip_id in dict.fromkeys(clip_ids):
        try:
            clip, track = project.clip_and_track(clip_id)
        except KeyError:
            raise EditError("error.edit.no_clip", clip_id=clip_id) from None
        parts.append(_Part(track.id, clip, clip.start, clip.offset,
                           clip.length, clip.fade_in, clip.fade_out))
    if not parts:
        # Nothing was selected to copy, like an edit with no clips.
        raise EditError("error.edit.no_selection")
    return _entry(project, parts, name, moment)


def make_entry_range(project: Project, start: int, end: int,
                     track_ids: Iterable[str] | None = None, *,
                     name: str = "",
                     now: float | None = None) -> Entry:
    """An entry holding the stretch ``[start, end)`` of the chosen tracks.

    ``track_ids`` ``None`` means every track. A clip reaching outside the
    stretch is trimmed to it: the offset moves with the start, and a fade
    is kept only where the clip's own edge is kept, clamped to the trimmed
    length, as ``ops`` trims it. The envelope is carried as it is: it is in
    source frames, so it stays attached to the kept audio. A range that
    catches no clip — an empty or reversed one catches none — raises, as
    does a track the project does not have. The entry's span is the clips'
    cover, so silent edges of the stretch are not part of the copy.
    """
    moment = time.time() if now is None else float(now)
    parts = []
    for track in _chosen_tracks(project, track_ids):
        for clip in track.clips:
            new_start = max(clip.start, int(start))
            new_end = min(clip.end, int(end))
            if new_start >= new_end:
                continue
            length = new_end - new_start
            fade_in = min(clip.fade_in, length) if new_start == clip.start else 0
            fade_out = min(clip.fade_out, length) if new_end == clip.end else 0
            parts.append(_Part(track.id, clip, new_start,
                               clip.offset + (new_start - clip.start), length,
                               fade_in, fade_out))
    if not parts:
        raise EditError("error.edit.no_selection")
    return _entry(project, parts, name, moment)


# -- JSON --------------------------------------------------------------------

_REF_KEYS = ("media_sha256", "offset", "length", "gain_db", "pan", "fade_in",
             "fade_out", "muted", "envelope", "rel_start", "track_slot")
_ENTRY_KEYS = ("id", "name", "created_utc", "refs", "span", "source_project",
               "pinned")


def _ref_out(ref: ClipRef) -> dict:
    d = {"media_sha256": ref.media_sha256, "offset": ref.offset,
         "length": ref.length, "gain_db": ref.gain_db, "pan": ref.pan,
         "fade_in": ref.fade_in, "fade_out": ref.fade_out,
         "muted": ref.muted,
         "envelope": [[frame, db] for frame, db in ref.envelope],
         "rel_start": ref.rel_start, "track_slot": ref.track_slot}
    # A known key always wins over an extra of the same name.
    return {**ref.extra, **d}


def _ref_in(d: dict) -> ClipRef:
    known = {key: d[key] for key in _REF_KEYS if key in d}
    known["envelope"] = tuple(
        (int(frame), float(db)) for frame, db in known.get("envelope", ()))
    extra = {key: value for key, value in d.items() if key not in _REF_KEYS}
    return ClipRef(**known, extra=extra)


def _entry_out(entry: Entry) -> dict:
    d = {"id": entry.id, "name": entry.name,
         "created_utc": entry.created_utc,
         "refs": [_ref_out(ref) for ref in entry.refs],
         "span": [entry.span[0], entry.span[1]],
         "source_project": entry.source_project, "pinned": entry.pinned}
    # A known key always wins over an extra of the same name.
    return {**entry.extra, **d}


def _entry_in(d: dict) -> Entry:
    known = {key: d[key] for key in _ENTRY_KEYS if key in d}
    known["refs"] = tuple(_ref_in(ref) for ref in known.get("refs", ()))
    if "span" in known:
        known["span"] = (int(known["span"][0]), int(known["span"][1]))
    extra = {key: value for key, value in d.items() if key not in _ENTRY_KEYS}
    return Entry(**known, extra=extra)


def to_json(entry: Entry) -> str:
    """The entry as clipboard JSON (WP20's text clipboard format)."""
    return json.dumps(_entry_out(entry), separators=(",", ":"))


def from_json(text: str) -> Entry:
    """The entry in ``text``; unknown keys are kept and re-emitted."""
    return _entry_in(json.loads(text))


def prune_entries(entries: Iterable[Entry], max_unpinned: int) -> list[Entry]:
    """``entries`` (newest first) without the oldest unpinned ones beyond
    ``max_unpinned``. Pinned entries are always kept, in place, and do not
    count toward the limit. At least the newest entry survives, so a fresh
    copy is never lost to a limit of 0."""
    items = list(entries)
    budget = max(1, int(max_unpinned))
    kept: list[Entry] = []
    for item in items:
        if item.pinned:
            kept.append(item)
        elif budget > 0:
            budget -= 1
            kept.append(item)
    return kept


class ClipboardHistory:
    """The clipboard's entries, newest first, kept as references.

    ``max_entries`` limits the *unpinned* entries (``prune_entries``): adding
    beyond it drops the oldest unpinned ones, a pinned entry is never
    dropped, and pinned entries do not count toward the limit.
    """

    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = int(max_entries)
        self._entries: list[Entry] = []
        # Unknown keys a newer kuulas wrote (docs/FORMAT.md, "Unknown keys").
        self.extra: dict = {}

    def add(self, entry: Entry) -> None:
        """Add ``entry`` at the front, then prune the oldest unpinned."""
        self._entries.insert(0, entry)
        self._entries = prune_entries(self._entries, self.max_entries)

    def _find(self, entry_id: str) -> Entry:
        for item in self._entries:
            if item.id == entry_id:
                return item
        raise KeyError(entry_id)

    def _replace(self, entry_id: str, **changes: object) -> None:
        entry = self._find(entry_id)
        fresh = replace(entry, **changes)
        self._entries = [fresh if item.id == entry.id else item
                         for item in self._entries]

    def pin(self, entry_id: str) -> None:
        """Pin an entry, so pruning keeps it."""
        self._replace(entry_id, pinned=True)

    def unpin(self, entry_id: str) -> None:
        """Let an entry be pruned again (and prune now if it is over the limit)."""
        self._replace(entry_id, pinned=False)
        self._entries = prune_entries(self._entries, self.max_entries)

    def rename(self, entry_id: str, name: str) -> None:
        """Give an entry a new name."""
        self._replace(entry_id, name=name)

    def delete(self, entry_id: str) -> None:
        """Take an entry out of the history."""
        entry = self._find(entry_id)
        self._entries = [item for item in self._entries if item.id != entry.id]

    def get(self, entry_id: str) -> Entry | None:
        """The entry with ``entry_id``, or None if the history has none."""
        return next(
            (item for item in self._entries if item.id == entry_id), None)

    def entries(self) -> tuple[Entry, ...]:
        """All entries, newest first."""
        return tuple(self._entries)

    def to_json(self) -> str:
        """The whole history as clipboard JSON, entries newest first."""
        d = {"max_entries": self.max_entries,
             "entries": [_entry_out(entry) for entry in self._entries]}
        return json.dumps({**self.extra, **d}, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> ClipboardHistory:
        """The history in ``text``; unknown keys are kept and re-emitted."""
        d = json.loads(text)
        history = cls(int(d.get("max_entries", 50)))
        history._entries = [_entry_in(entry) for entry in d.get("entries", [])]
        history.extra = {key: value for key, value in d.items()
                         if key not in ("max_entries", "entries")}
        return history
