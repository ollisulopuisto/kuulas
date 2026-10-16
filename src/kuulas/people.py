"""People, interviews and who speaks (WP41; docs/FORMAT.md, "People, interviews
and bits").

A *person* is someone who speaks; an *interview* is one sitting, which any
number of recorders captured, so the same conversation recorded on A's mic,
B's mic and a Zoom mix links together. Both are **material**: they live in
the material root (``people``, ``interviews``, ``media_person``,
``speakers``), so every edit sees them and changing them is an undoable
step. In a series the same records are one JSON file each (``series``);
projects refer to people by id either way.

**Who speaks** is resolved when words are read, never stored in them: a mic
file has ``media.person``; a mix's transcription labels (``spk``) map to
people through a map kept per transcript revision. Stored words are not
touched, so a corrected map changes nobody's text, and a re-transcription
starts with an empty map of its own.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path

from .model import _out, _split


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    aliases: tuple[str, ...] = ()
    role: str = ""  # "host" | "guest" | …
    notes: str = ""
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self, aliases=list(self.aliases))

    @classmethod
    def from_dict(cls, d: dict) -> Person:
        known, extra = _split(cls, d)
        known["aliases"] = tuple(known.get("aliases", ()))
        return cls(**known, extra=extra)


@dataclass(frozen=True)
class Interview:
    """One recording session. ``media`` holds sha256 digests (content identity,
    so it survives re-import and travels between projects); ``participants``
    are ``{"person": id, "role": str}``."""

    id: str
    title: str = ""
    date: str = ""  # ISO date, optionally with a UTC time
    place: str = ""
    participants: tuple[dict, ...] = field(default=(), hash=False)
    media: tuple[str, ...] = ()
    sync_group: str = ""
    notes: str = ""
    tags: tuple[str, ...] = ()
    extra: dict = field(default_factory=dict, hash=False)

    def to_dict(self) -> dict:
        return _out(self, participants=[dict(p) for p in self.participants],
                    media=list(self.media), tags=list(self.tags))

    @classmethod
    def from_dict(cls, d: dict) -> Interview:
        known, extra = _split(cls, d)
        known["participants"] = tuple(dict(p) for p in known.get("participants", ()))
        known["media"] = tuple(known.get("media", ()))
        known["tags"] = tuple(known.get("tags", ()))
        return cls(**known, extra=extra)


# -- who speaks ------------------------------------------------------------------


def resolve_words(words: list[dict], media_person: str,
                  label_map: Mapping[str, str]) -> list[dict]:
    """``words`` with ``person`` set where it is known; the input is not changed.

    A speaker label with an entry in ``label_map`` is that entry (an empty
    entry means "nobody", and the media's person does not take over); any
    other word belongs to the media's person, if it has one. Words with no
    known person come back as they were.
    """
    if not media_person and not label_map:
        return words
    out = []
    for w in words:
        label = w.get("spk", "")
        person = (label_map[label] or "") if label in label_map else media_person
        out.append({**w, "person": person} if person else w)
    return out


@dataclass(frozen=True)
class Passage:
    """A run of one person's words in one recording.

    ``start``/``end`` are flicks from the media's start; ``recording_*`` are
    on the media's sync group clock (``group``), which is what makes passages
    from different mics of one interview comparable, and what WP38's usage
    marks are keyed on. ``None`` when the media is in no group.
    """

    person: str
    media: str
    start: int
    end: int
    text: str
    first_word: int
    last_word: int
    group: str | None = None
    recording_start: int | None = None
    recording_end: int | None = None
    project: Path | None = None


def find_passages(person: str, words_by_media: Mapping[str, list[dict]],
                  sync_of: Callable[[str], tuple[str, int] | None]) -> list[Passage]:
    """Every passage by ``person``: consecutive words they speak, split where
    anyone else speaks in between. ``words_by_media`` is resolved
    (``resolve_words``); ``sync_of(media)`` is ``(group id, origin flicks)`` or None."""
    if not person:
        return []
    out = []
    for media in sorted(words_by_media):
        sync = sync_of(media)
        group, origin = sync if sync else (None, 0)
        words = words_by_media[media]
        runs = groupby(enumerate(words), lambda iw: iw[1].get("person") == person)
        for mine, grouped in runs:
            if not mine:
                continue
            run = list(grouped)
            (first, a), (last, b) = run[0], run[-1]
            out.append(Passage(
                person, media, a["s"], b["e"], " ".join(w["w"] for _, w in run),
                first, last, group,
                None if sync is None else origin + a["s"],
                None if sync is None else origin + b["e"]))
    return out
