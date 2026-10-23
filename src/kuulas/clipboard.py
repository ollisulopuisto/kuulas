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
    # The recording's file name when it was copied: for people reading the
    # entry (panel, search), never an identity (that is ``media_sha256``), so
    # it takes no part in comparing two references.
    media_name: str = field(default="", compare=False)
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

    The rest is what later sorting and searching read (WP65), kept in the
    entry so it still means something when its project is gone or far away:
    ``source_name`` and ``source_id`` (the project's name and manifest id),
    ``tracks`` and ``track_kinds`` (the source tracks' names and kinds by
    slot), ``text`` (the transcript words inside the copied stretch, one line
    per track), ``shared`` (marked as worth sharing across projects) and
    ``adopted_from`` (the folder of the project an adopted copy came from).
    Every one defaults, so an entry from before loads.
    """

    id: str
    name: str
    created_utc: float
    refs: tuple[ClipRef, ...] = ()
    span: tuple[int, int] = (0, 0)
    source_project: str = ""
    pinned: bool = False
    source_name: str = ""
    source_id: str = ""
    tracks: tuple[str, ...] = ()
    track_kinds: tuple[str, ...] = ()
    text: str = ""
    shared: bool = False
    adopted_from: str = ""
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


def _media_name(project: Project, clip: Clip) -> str:
    """The file name of the recording behind a clip ("" when it has none)."""
    try:
        return project.media_item(clip.media).name
    except KeyError:
        return ""


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
                 rel_start=part.start - base, track_slot=slots[part.track_id],
                 media_name=_media_name(project, part.clip))
         for part in parts),
        key=lambda ref: (ref.rel_start, ref.track_slot, ref.offset)))
    end = max(part.start + part.length for part in parts)
    # The source tracks' names and kinds by slot, so the panel can say where a
    # copy came from without the source project.
    source = [track for track in project.tracks if track.id in touched]
    return Entry(_new_id(moment), name, moment, refs=refs, span=(base, end),
                 tracks=tuple(track.name for track in source),
                 track_kinds=tuple(track.kind for track in source))


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


def entry_from_refs(refs: Iterable[ClipRef], *, name: str, span: tuple[int, int],
                    source_project: str = "", pinned: bool = False,
                    extra: dict | None = None, now: float | None = None) -> Entry:
    """An entry built from ready-made references (an import, not a copy)."""
    moment = time.time() if now is None else float(now)
    return Entry(_new_id(moment), name, moment, refs=tuple(refs), span=span,
                 source_project=source_project, pinned=pinned, extra=dict(extra or {}))


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
             "fade_out", "muted", "envelope", "rel_start", "track_slot", "media_name")
_ENTRY_KEYS = ("id", "name", "created_utc", "refs", "span", "source_project",
               "pinned", "source_name", "source_id", "tracks", "track_kinds", "text",
               "shared", "adopted_from")


def _ref_out(ref: ClipRef) -> dict:
    d = {"media_sha256": ref.media_sha256, "offset": ref.offset,
         "length": ref.length, "gain_db": ref.gain_db, "pan": ref.pan,
         "fade_in": ref.fade_in, "fade_out": ref.fade_out,
         "muted": ref.muted,
         "envelope": [[frame, db] for frame, db in ref.envelope],
         "rel_start": ref.rel_start, "track_slot": ref.track_slot,
         "media_name": ref.media_name}
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
         "source_project": entry.source_project, "pinned": entry.pinned,
         "source_name": entry.source_name, "source_id": entry.source_id,
         "tracks": list(entry.tracks), "track_kinds": list(entry.track_kinds),
         "text": entry.text, "shared": entry.shared,
         "adopted_from": entry.adopted_from}
    # A known key always wins over an extra of the same name.
    return {**entry.extra, **d}


def _entry_in(d: dict) -> Entry:
    known = {key: d[key] for key in _ENTRY_KEYS if key in d}
    known["refs"] = tuple(_ref_in(ref) for ref in known.get("refs", ()))
    if "span" in known:
        known["span"] = (int(known["span"][0]), int(known["span"][1]))
    for key in ("tracks", "track_kinds"):
        if key in known:
            known[key] = tuple(str(item) for item in known[key])
    extra = {key: value for key, value in d.items() if key not in _ENTRY_KEYS}
    return Entry(**known, extra=extra)


def entry_from_view(d: object) -> Entry:
    """An entry from the dict the panel got from the API and sends back to adopt it.

    The API view carries computed keys (``length``, ``clips``, ``missing_here``
    ...) beside the data; only the keys an entry has are taken, the rest are
    dropped, so a view never leaks into a file. Raises ``EditError``
    (``error.clipboard.bad_entry``) when what is left is not a usable entry: no
    references, or a reference without a SHA-256 recording, a non-negative offset
    and a positive length."""
    if not isinstance(d, dict):
        raise EditError("error.clipboard.bad_entry")
    refs = d.get("refs")
    if not isinstance(refs, list) or not refs:
        raise EditError("error.clipboard.bad_entry")
    clean = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise EditError("error.clipboard.bad_entry")
        digest = ref.get("media_sha256")
        offset, length = ref.get("offset"), ref.get("length")
        ints = all(isinstance(n, int) and not isinstance(n, bool)
                   for n in (offset, length))
        valid = isinstance(digest, str) and len(digest) == 64
        ok = valid and ints and offset >= 0 < length
        if not ok:
            raise EditError("error.clipboard.bad_entry")
        clean.append({key: ref[key] for key in _REF_KEYS if key in ref})
    kept = {key: d[key] for key in _ENTRY_KEYS if key in d}
    kept["refs"] = clean
    if "id" not in kept:
        kept["id"] = _new_id(time.time())
    kept.setdefault("name", "")
    kept.setdefault("created_utc", 0.0)
    try:
        return _entry_in(kept)
    except (TypeError, KeyError, IndexError, AttributeError, ValueError):
        raise EditError("error.clipboard.bad_entry") from None


def adopted_copy(entry: Entry, *, from_project: str = "",
                 now: float | None = None) -> Entry:
    """``entry`` as this project's own copy: a new id, made now (so it is the
    newest), not shared (the copy here is this project's own), and
    ``adopted_from`` the project it came from. Its media are still looked for
    where the original's were (``source_project``, or ``from_project`` when the
    original did not say). The original's time is kept as ``adopted_created_utc``."""
    moment = time.time() if now is None else float(now)
    return replace(entry, id=_new_id(moment), created_utc=moment, shared=False,
                   adopted_from=from_project or entry.source_project,
                   source_project=entry.source_project or from_project,
                   pinned=False, extra={"adopted_created_utc": entry.created_utc})


def same_content(a: Entry, b: Entry) -> bool:
    """Whether ``b`` is already ``a`` on a shelf (docs/design/CLIPBOARD-SHELVES.md):
    the same id, or the same references (recordings by hash, windows, layout; names
    take no part) covering the same length. Where it was copied does not matter."""
    if a.id == b.id:
        return True
    return (a.refs == b.refs
            and a.span[1] - a.span[0] == b.span[1] - b.span[0])


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

    ``max_entries`` ``None`` (the default, and what the stores use) means no
    limit: nothing is ever dropped silently (WP65). With a number, it limits
    the *unpinned* entries (``prune_entries``): adding beyond it drops the
    oldest unpinned ones, a pinned entry is never dropped. The only prune in
    the app is the explicit "Clear old entries" (``prune``).
    """

    def __init__(self, max_entries: int | None = None) -> None:
        self.max_entries = None if max_entries is None else int(max_entries)
        self._entries: list[Entry] = []
        # Unknown keys a newer kuulas wrote (docs/FORMAT.md, "Unknown keys").
        self.extra: dict = {}

    def add(self, entry: Entry) -> None:
        """Add ``entry`` at the front, then prune the oldest unpinned."""
        self._entries.insert(0, entry)
        if self.max_entries is not None:
            self._entries = prune_entries(self._entries, self.max_entries)

    def put(self, entry: Entry) -> None:
        """Replace the entry with ``entry``'s id in place, or add it at the front."""
        if any(item.id == entry.id for item in self._entries):
            self._entries = [entry if item.id == entry.id else item
                             for item in self._entries]
        else:
            self.add(entry)

    def set_shared(self, entry_id: str, shared: bool) -> None:
        """Mark an entry as shared (or not); the flag only, nothing moves."""
        self._replace(entry_id, shared=bool(shared))

    def merge(self, entries: Iterable[Entry]) -> int:
        """Add the entries whose id is not here yet; return how many came in.
        The list stays newest first (by ``created_utc``, ties keep their place)."""
        have = {item.id for item in self._entries}
        fresh = [item for item in entries if item.id not in have]
        if fresh:
            self._entries = sorted([*self._entries, *fresh],
                                   key=lambda item: -item.created_utc)
        return len(fresh)

    def remove(self, entry_ids: Iterable[str]) -> int:
        """Take the entries with these ids out; return how many were here."""
        gone = set(entry_ids)
        before = len(self._entries)
        self._entries = [item for item in self._entries if item.id not in gone]
        return before - len(self._entries)

    def prune(self, keep: int) -> int:
        """Drop the oldest unpinned entries beyond the newest ``keep`` (at
        least one); return how many went. The explicit "Clear old entries"."""
        before = len(self._entries)
        self._entries = prune_entries(self._entries, keep)
        return before - len(self._entries)

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
        if self.max_entries is not None:
            self._entries = prune_entries(self._entries, self.max_entries)

    def rename(self, entry_id: str, name: str) -> None:
        """Give an entry a new name."""
        self._replace(entry_id, name=name)

    def delete(self, entry_id: str) -> None:
        """Take an entry out of the history."""
        entry = self._find(entry_id)
        self._entries = [item for item in self._entries if item.id != entry.id]

    def move(self, entry_id: str, before: str | None) -> None:
        """Put an entry just before ``before`` (None: at the end), the owner's drag
        in the Clipboard tab. The list is the order shown, and so the order Paste reads
        (the first is pasted); a new copy still goes to the front. ``KeyError`` for an
        unknown id."""
        entry = self._find(entry_id)
        if before == entry_id:
            return
        if before is not None:
            self._find(before)
        rest = [item for item in self._entries if item.id != entry_id]
        at = len(rest) if before is None else next(
            i for i, item in enumerate(rest) if item.id == before)
        rest.insert(at, entry)
        self._entries = rest

    def get(self, entry_id: str) -> Entry | None:
        """The entry with ``entry_id``, or None if the history has none."""
        return next(
            (item for item in self._entries if item.id == entry_id), None)

    def entries(self) -> tuple[Entry, ...]:
        """All entries, newest first."""
        return tuple(self._entries)

    def to_json(self) -> str:
        """The whole history as clipboard JSON, entries newest first."""
        d: dict = {"entries": [_entry_out(entry) for entry in self._entries]}
        if self.max_entries is not None:
            d["max_entries"] = self.max_entries
        return json.dumps({**self.extra, **d}, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> ClipboardHistory:
        """The history in ``text``; unknown keys are kept and re-emitted."""
        d = json.loads(text)
        limit = d.get("max_entries")
        history = cls(None if limit is None else int(limit))
        history._entries = [_entry_in(entry) for entry in d.get("entries", [])]
        history.extra = {key: value for key, value in d.items()
                         if key not in ("max_entries", "entries")}
        return history
