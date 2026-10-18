"""Cut candidates (WP18): proposed cuts, found or marked, never applied by themselves.

A candidate names a stretch of a *recording*, never of the timeline: a media id
and ``[start, end)`` in flicks from that media's start, the same clock as
transcript words (docs/FORMAT.md). Its timeline position is derived from the
clips every time (``place``), so it follows its audio through every later move,
trim and cut, and an id made from the recording range (``candidate_id``) stays
the same however the edit changes. A candidate in a sync group is anchored to
the group's main recording and covers every track of the group.

Kinds: ``silence`` (nobody speaks for ``MIN_SILENCE_S``), ``filler`` (a
hesitation or a discourse filler from the transcript), ``retake`` (a word or
phrase said again at once: the first take is the cut), ``breath`` (reserved:
the level analysis cannot yet tell a breath from speech, so nothing makes it)
and ``marked`` (the user's D key). States: ``open``, ``cut`` (accepted),
``kept`` (rejected: never proposed again).

This module is pure: project, transcripts and optional silence data in,
candidates and plans out. It reads no audio. The session stores the
candidates in the material root under ``candidates`` (``{id: record}``), so
every edit sees them and each change is one undoable material step.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple

from . import edit_scope, ops
from .clock import FLICKS, flicks_to_frames, frames_to_flicks
from .gate import split_by_gate
from .messages import language, t
from .model import Project

KINDS = ("silence", "filler", "retake", "breath", "marked")
STATES = ("open", "cut", "kept")
#: ``track``: applies to the tracks that play the candidate's own recording
#: (the speaker's mic). ``group``: to every track of its sync group (WP19a).
SCOPES = ("track", "group")
#: ``soft``: mute in place, the gap stays (the owner's Delete, 18.10.2026; the
#: default). ``ripple``: remove and close the gap (Cut, X).
MODES = ("soft", "ripple")

#: A pause this long with nobody speaking is dead air worth a look. Pauses
#: inside a turn are mostly under a second and turn gaps around 0.2 s in
#: conversation; 1.5 s is where a listener starts to hear "nothing happening".
#: Not measured on the owner's recordings yet: tune it there.
MIN_SILENCE_S = 1.5
#: A cut pause leaves this much silence (half on each side), so the cut sounds
#: like a natural pause rather than two words glued together.
KEEP_PAUSE_S = 0.5
#: Fillers closer than this ("öö, öö") are one candidate: one decision, and no
#: 0.1 s sliver of breath left between two muted pieces.
FILLER_JOIN_S = 0.3
#: A phrase said again within this many seconds (start to start) is a retake.
#: A false start is re-said at once; the same words a sentence later are
#: usually on purpose.
REPEAT_WINDOW_S = 4.0
#: The longest phrase compared. Longer restarts are rare and already caught by
#: their last words; the search is quadratic in this.
MAX_REPEAT_WORDS = 4
#: Share of a candidate that must still be heard to propose it: a stretch
#: already muted, gated or cut away is not proposed again. Not 1.0, because
#: frame rounding at a clip edge would otherwise hide a candidate that touches one.
MIN_HEARD = 0.9
#: The store's bound. A busy hour has a few hundred fillers and pauses;
#: every material revision stores the whole root, so the list must not grow
#: without limit. The weakest open candidates go first; decisions stay.
MAX_CANDIDATES = 1000
#: "Play as if cut" plays this much before and after the candidate (WP18).
PREVIEW_PAD_S = 2.0

#: Fillers per language. ``hesitation``: patterns (whole word, lower case, no
#: punctuation) for the sounds of thinking, almost always safe to cut.
#: ``discourse``: words that are fillers in speech but can carry meaning
#: ("niinku" as "like"), so they score lower. English "like", "you know" and
#: "so" are left out: they are real words too often to propose blindly.
#: Whisper often drops hesitations from its text; what it drops is not found.
FILLERS: dict[str, dict[str, Any]] = {
    "en": {"hesitation": (r"u+h+", r"u+h*m+", r"e+r+m*", r"h+m+", r"m+", r"m+h+m+",
                          r"a+h+"),
           "discourse": ()},
    "fi": {"hesitation": (r"ö+h*", r"ä+h*", r"e+h*", r"y+h*", r"h+m+", r"m+",
                          r"m+h+m+"),
           "discourse": ("niinku", "niinkun", "tota", "totota", "tuota", "totanoin",
                         "elikkä")},
}

#: Scores: how sure a candidate is, 0..1, for ordering and for the bound.
SCORE_HESITATION = 0.9
SCORE_DISCOURSE = 0.5
SCORE_MARKED = 1.0

#: When two candidates overlap, the merged one takes the kind first in this list.
_PRIORITY = ("marked", "retake", "filler", "silence", "breath")

_NOT_WORD = re.compile(r"[^\w]+")


class CandidateError(ops.EditError):
    """A candidate request that cannot be done; nothing changed."""


class UnknownCandidateError(CandidateError):
    """No candidate with that id."""


@dataclass(frozen=True)
class Candidate:
    """One proposed cut. ``start``/``end``: flicks from ``media``'s start.
    ``reason``: ``{"key", "params"}``, a message translated when shown.
    ``extra``: keys a newer kuulas wrote, carried along unchanged."""

    id: str
    kind: str
    media: str
    start: int
    end: int
    scope: str = "track"
    state: str = "open"
    score: float = 0.0
    reason: dict = field(default_factory=dict, hash=False)
    text: str = ""
    extra: dict = field(default_factory=dict, hash=False)

    def record(self) -> dict:
        """The material root's record (the id is its key)."""
        return {**self.extra, "kind": self.kind, "media": self.media,
                "start": int(self.start), "end": int(self.end), "scope": self.scope,
                "state": self.state, "score": round(float(self.score), 3),
                "reason": dict(self.reason), "text": self.text}

    @classmethod
    def from_record(cls, cid: str, rec: dict) -> Candidate:
        known = {"kind", "media", "start", "end", "scope", "state", "score",
                 "reason", "text"}
        return cls(id=cid, kind=str(rec.get("kind", "marked")),
                   media=str(rec.get("media", "")), start=int(rec.get("start", 0)),
                   end=int(rec.get("end", 0)), scope=str(rec.get("scope", "track")),
                   state=str(rec.get("state", "open")),
                   score=float(rec.get("score", 0.0)),
                   reason=dict(rec.get("reason") or {}), text=str(rec.get("text", "")),
                   extra={k: v for k, v in rec.items() if k not in known})


class Piece(NamedTuple):
    """Where a clip plays part of a candidate: timeline frames ``[start, end)``."""

    track: str
    clip: str
    media: str
    start: int
    end: int


@dataclass(frozen=True)
class Plan:
    """What accepting a candidate does. ``project``: the result. ``spans``:
    the timeline ranges it cuts (sorted, as they are before the edit).
    ``preview``: for "play as if cut": play ``from``..``to`` skipping ``skip``."""

    mode: str
    spans: tuple[tuple[int, int], ...]
    tracks: tuple[str, ...]
    project: Project
    preview: dict


def candidate_id(media_sha256: str, kind: str, start: int, end: int) -> str:
    """Stable id: the same recording range and kind always get the same id,
    so a second detection finds the decisions made on the first."""
    key = f"{media_sha256}|{kind}|{int(start)}|{int(end)}".encode()
    return "k" + hashlib.sha256(key).hexdigest()[:16]


def _sha(p: Project, media_id: str) -> str:
    try:
        return p.media_item(media_id).sha256 or media_id
    except KeyError:
        return media_id


# -- range arithmetic (flicks) -------------------------------------------------


def _union(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in sorted((int(a), int(b)) for a, b in ranges if b > a):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


#: Half-open ranges, in flicks unless said otherwise.
Ranges = list[tuple[int, int]]


def _complement(ranges: Iterable[tuple[int, int]], lo: int, hi: int) -> Ranges:
    out, at = [], lo
    for a, b in _union(ranges):
        if a > at:
            out.append((at, min(a, hi)))
        at = max(at, b)
    if at < hi:
        out.append((at, hi))
    return [(a, b) for a, b in out if b > a]


def _intersect(x: Ranges, y: Ranges) -> Ranges:
    out, i, j = [], 0, 0
    x, y = _union(x), _union(y)
    while i < len(x) and j < len(y):
        a, b = max(x[i][0], y[j][0]), min(x[i][1], y[j][1])
        if a < b:
            out.append((a, b))
        if x[i][1] < y[j][1]:
            i += 1
        else:
            j += 1
    return out


# -- words ---------------------------------------------------------------------


def _norm(word: str) -> str:
    return _NOT_WORD.sub("", str(word).lower())


def is_filler(word: str, lang: str | None = None) -> str | None:
    """``"hesitation"``, ``"discourse"`` or None. ``lang``: only that
    language's table; None tries every language (the transcript's language is
    not always known, and the tables do not clash)."""
    w = _norm(word)
    if not w:
        return None
    tables = [FILLERS[lang]] if lang in FILLERS else list(FILLERS.values())
    for table in tables:
        if any(re.fullmatch(pat, w) for pat in table["hesitation"]):
            return "hesitation"
    for table in tables:
        if w in table["discourse"]:
            return "discourse"
    return None


def _fillers(p: Project, media_id: str, words: list[dict],
             lang: str | None) -> list[Candidate]:
    out: list[Candidate] = []
    run: list[tuple[dict, str]] = []

    def flush() -> None:
        if not run:
            return
        start, end = int(run[0][0]["s"]), int(run[-1][0]["e"])
        text = " ".join(str(w["w"]).strip() for w, _ in run)
        score = max(SCORE_HESITATION if tier == "hesitation" else SCORE_DISCOURSE
                    for _, tier in run)
        out.append(Candidate(
            id=candidate_id(_sha(p, media_id), "filler", start, end), kind="filler",
            media=media_id, start=start, end=end, score=score, text=text,
            reason={"key": "candidate.reason.filler", "params": {"word": text}}))
        run.clear()

    join = round(FILLER_JOIN_S * FLICKS)
    for w in words:
        tier = is_filler(w["w"], lang)
        if tier is None:
            flush()
            continue
        if run and int(w["s"]) - int(run[-1][0]["e"]) > join:
            flush()
        run.append((w, tier))
    flush()
    return out


def _retakes(p: Project, media_id: str, words: list[dict]) -> list[Candidate]:
    """A phrase of 1..MAX_REPEAT_WORDS words said again at once. Fillers in
    between are ignored ("I went, um, I went"), and the cut runs from the first
    take's start to the second take's start, fillers included."""
    toks = [(n, w) for w in words if not is_filler(w["w"]) and (n := _norm(w["w"]))]
    window = round(REPEAT_WINDOW_S * FLICKS)
    out: list[Candidate] = []
    i = 0
    while i < len(toks):
        for n in range(min(MAX_REPEAT_WORDS, (len(toks) - i) // 2), 0, -1):
            first = [x for x, _ in toks[i:i + n]]
            second = [x for x, _ in toks[i + n:i + 2 * n]]
            start, again = int(toks[i][1]["s"]), int(toks[i + n][1]["s"])
            if first == second and again - start <= window and again > start:
                text = " ".join(_NOT_WORD.sub(" ", str(w["w"])).strip()
                                for _, w in toks[i:i + n])
                # A single repeated word is often emphasis ("very, very").
                score = 0.4 if n == 1 else min(0.9, 0.6 + 0.1 * (n - 1))
                out.append(Candidate(
                    id=candidate_id(_sha(p, media_id), "retake", start, again),
                    kind="retake", media=media_id, start=start, end=again,
                    score=score, text=text,
                    reason={"key": "candidate.reason.retake", "params": {"text": text}}))
                i += n
                break
        else:
            i += 1
    return out


# -- silences ------------------------------------------------------------------


def _units(p: Project) -> list[tuple[str | None, str, dict[str, int]]]:
    """Recording clocks to look for silence on: ``(group id or None, anchor
    media, {member media: origin flicks})``. Only media some clip plays count."""
    used = {c.media for tr in p.tracks for c in tr.clips}
    groups: dict[str, dict[str, int]] = {}
    out: list[tuple[str | None, str, dict[str, int]]] = []
    for m in p.media:
        if m.id not in used:
            continue
        found = p.sync_member(m.id)
        if found is None:
            out.append((None, m.id, {m.id: 0}))
        else:
            groups.setdefault(found[0].id, {})[m.id] = found[1]
    for g in p.sync_groups:
        members = groups.get(g.id)
        if members:
            out.append((g.id, g.main, members))
    return out


def _silences(p: Project, transcripts: dict[str, list[dict]],
              silences: dict[str, list[tuple[int, int]]]) -> list[Candidate]:
    """Pauses where no member of a clock speaks. A member's quiet comes from
    its transcript (the gaps between its words), from level data, or from
    both (intersected: levels end a pause where the words' timing runs on);
    a member with neither makes the whole clock unknown, so nothing is guessed.
    Quiet before the first and after the last sound is left alone."""
    out: list[Candidate] = []
    need = round(MIN_SILENCE_S * FLICKS)
    keep = round(KEEP_PAUSE_S * FLICKS) // 2
    for group, anchor, members in _units(p):
        extents = {m: (o, o + frames_to_flicks(p.media_item(m).frames, p.rate))
                   for m, o in members.items()}
        lo = min(a for a, _ in extents.values())
        hi = max(b for _, b in extents.values())
        quiet: list[tuple[int, int]] | None = [(lo, hi)]
        for m, origin in members.items():
            mine = None
            if m in transcripts:
                said = [(int(w["s"]) + origin, int(w["e"]) + origin)
                        for w in transcripts[m]]
                mine = _complement(said, lo, hi)
            if m in silences:
                level = [(int(a) + origin, int(b) + origin) for a, b in silences[m]]
                # Outside the member's own file there is nothing to hear from it.
                level += _complement([extents[m]], lo, hi)
                mine = level if mine is None else _intersect(mine, level)
            if mine is None:
                quiet = None
                break
            quiet = _intersect(quiet, mine)
        if not quiet:
            continue
        shift = members.get(anchor)
        if shift is None:
            found = p.sync_member(anchor)
            shift = found[1] if found is not None else 0
        for a, b in quiet:
            if a <= lo or b >= hi or b - a < need:
                continue
            start, end = a + keep - shift, b - keep - shift
            seconds = round((b - a) / FLICKS, 1)
            out.append(Candidate(
                id=candidate_id(_sha(p, anchor), "silence", start, end), kind="silence",
                media=anchor, start=start, end=end,
                scope="group" if group else "track",
                score=round(min(1.0, 0.5 + (b - a - need) / (10 * FLICKS)), 3),
                reason={"key": "candidate.reason.silence",
                        "params": {"seconds": seconds}}))
    return out


# -- placement -------------------------------------------------------------------


def _targets(p: Project, c: Candidate) -> dict[str, tuple[int, int]]:
    """The recordings a candidate covers, each with the range on its own clock."""
    if c.scope == "group":
        found = p.sync_member(c.media)
        if found is not None:
            group, origin = found
            out = {}
            for m in p.media:
                other = p.sync_member(m.id)
                if other is not None and other[0].id == group.id:
                    delta = origin - other[1]
                    out[m.id] = (c.start + delta, c.end + delta)
            if out:
                return out
    return {c.media: (c.start, c.end)}


def place(p: Project, c: Candidate) -> list[Piece]:
    """Every clip that plays part of the candidate, with where on the timeline.
    Empty when its audio has all been cut away."""
    targets = _targets(p, c)
    out = []
    for track in p.tracks:
        for clip in track.clips:
            rng = targets.get(clip.media)
            if rng is None:
                continue
            lo = frames_to_flicks(clip.offset, p.rate)
            hi = frames_to_flicks(clip.offset + clip.length, p.rate)
            a, b = max(rng[0], lo), min(rng[1], hi)
            if a >= b:
                continue
            s = clip.start + flicks_to_frames(a, p.rate) - clip.offset
            e = clip.start + flicks_to_frames(b, p.rate) - clip.offset
            if e > s:
                out.append(Piece(track.id, clip.id, clip.media, s, e))
    return out


def spans(p: Project, c: Candidate) -> list[tuple[int, int]]:
    """The candidate's timeline ranges, merged and sorted."""
    return _union((x.start, x.end) for x in place(p, c))


def heard(p: Project, c: Candidate) -> float:
    """Share of the candidate still heard on its best recording: clip mutes
    and gates count as not heard (a track's mute button does not: that is
    monitoring, not editing)."""
    want = max(1, flicks_to_frames(c.end - c.start, p.rate))
    by_media: dict[str, list[tuple[int, int]]] = {}
    for x in place(p, c):
        track = p.track(x.track)
        if p.clip(x.clip).muted:
            continue
        for a, b, is_open in split_by_gate(track.gate, x.start, x.end):
            if is_open:
                by_media.setdefault(x.media, []).append((a, b))
    best = max((sum(b - a for a, b in _union(r)) for r in by_media.values()), default=0)
    return min(1.0, best / want)


def _clock(p: Project, c: Candidate) -> tuple[tuple[str, str], int, int]:
    """A key and range on which candidates can be compared for overlap."""
    if c.scope == "group":
        found = p.sync_member(c.media)
        if found is not None:
            return ("group", found[0].id), c.start + found[1], c.end + found[1]
    return ("media", c.media), c.start, c.end


# -- detection -------------------------------------------------------------------


def merge_overlaps(p: Project, found: Iterable[Candidate]) -> list[Candidate]:
    """Overlapping candidates on the same clock become one: the union, the
    stronger kind (``_PRIORITY``), the higher score. Sorted by clock and start."""
    keyed = sorted(((_clock(p, c), c) for c in found),
                   key=lambda kc: (kc[0][0], kc[0][1], kc[0][2]))
    out: list[tuple[tuple, Candidate]] = []
    for (key, a, b), c in keyed:
        if out and out[-1][0][0] == key and a < out[-1][0][2]:
            (_, a0, b0), prev = out[-1]
            win = min((prev, c), key=lambda x: _PRIORITY.index(x.kind))
            lo, hi = min(a0, a), max(b0, b)
            shift = (prev.start - a0)  # back to the anchor's own clock
            start, end = lo + shift, hi + shift
            merged = replace(win, start=start, end=end, score=max(prev.score, c.score),
                             id=candidate_id(_sha(p, win.media), win.kind, start, end))
            out[-1] = ((key, lo, hi), merged)
        else:
            out.append(((key, a, b), c))
    return [c for _, c in out]


def detect(p: Project, transcripts: dict[str, list[dict]], *,
           silences: dict[str, list[tuple[int, int]]] | None = None,
           lang: str | None = None) -> list[Candidate]:
    """Every candidate the transcripts (and optional level silences: media id
    -> quiet ranges in flicks from its start) show, merged where they overlap,
    leaving out what is no longer heard. Ids are stable (``candidate_id``)."""
    known = {m.id for m in p.media}
    found: list[Candidate] = []
    for media_id, words in sorted(transcripts.items()):
        if media_id not in known or not words:
            continue
        ordered = sorted(words, key=lambda w: int(w["s"]))
        found += _fillers(p, media_id, ordered, lang)
        found += _retakes(p, media_id, ordered)
    found += _silences(p, {m: w for m, w in transcripts.items() if m in known},
                       {m: r for m, r in (silences or {}).items() if m in known})
    return merge_overlaps(p, [c for c in found if heard(p, c) >= MIN_HEARD])


# -- the store (material root ``candidates``) -------------------------------------


def _decided(rec: dict) -> bool:
    return rec.get("state", "open") != "open" or rec.get("kind") == "marked"


def merge(existing: dict[str, dict], found: Iterable[Candidate],
          p: Project) -> tuple[dict[str, dict], dict[str, int]]:
    """The store after a detection run, and ``{"added", "dropped"}``.

    Decisions (cut, kept) and user marks always stay. A found candidate with
    an id already stored keeps its record, decision included. A new one that
    overlaps a decision or a mark is not added: a kept stretch is not proposed
    again even when a corrected transcript moves it a little. Open candidates
    the run did not find again are dropped. Unknown record keys are kept.
    """
    out = {i: r for i, r in existing.items() if _decided(r)}
    blockers: dict[tuple, list[tuple[int, int]]] = {}
    for i, r in out.items():
        key, a, b = _clock(p, Candidate.from_record(i, r))
        blockers.setdefault(key, []).append((a, b))
    added = 0
    for c in found:
        if c.id in out:
            continue
        if c.id in existing:
            out[c.id] = existing[c.id]
            continue
        key, a, b = _clock(p, c)
        if any(x < b and a < y for x, y in blockers.get(key, ())):
            continue
        out[c.id] = c.record()
        added += 1
    if len(out) > MAX_CANDIDATES:
        ranked = sorted(out.items(), key=lambda kv: (not _decided(kv[1]),
                                                     -float(kv[1].get("score", 0)),
                                                     kv[0]))
        out = dict(ranked[:MAX_CANDIDATES])
        added = sum(1 for i in out if i not in existing)
    dropped = sum(1 for i in existing if i not in out)
    return out, {"added": added, "dropped": dropped}


def set_state(store: dict[str, dict], cid: str, state: str) -> dict[str, dict]:
    """The store with one candidate's state changed (open, cut or kept)."""
    if state not in STATES:
        raise CandidateError("error.candidates.bad_state", state=state)
    if cid not in store:
        raise UnknownCandidateError("error.candidates.no_candidate", id=cid)
    return {**store, cid: {**store[cid], "state": state}}


def get(store: dict[str, dict], cid: str) -> Candidate:
    if cid not in store:
        raise UnknownCandidateError("error.candidates.no_candidate", id=cid)
    return Candidate.from_record(cid, store[cid])


def summary(store: dict[str, dict]) -> dict[str, int]:
    counts = dict.fromkeys(STATES, 0)
    for r in store.values():
        state = r.get("state", "open")
        counts[state] = counts.get(state, 0) + 1
    return {**counts, "total": len(store)}


# -- marking and applying ------------------------------------------------------------


def mark(p: Project, start: int, end: int, track_id: str | None = None) -> Candidate:
    """A user's candidate (D, Alt+D) over timeline ``[start, end)``, anchored
    through the clip playing ``start`` on ``track_id`` (or the first track
    that plays it). Over a clip in a sync group it anchors to the group's
    clock and covers every track of the group. The range is clamped to that
    clip: past its end the timeline plays other audio."""
    start, end = int(start), int(end)
    if end <= start:
        raise ops.EditError("error.edit.empty_range")
    tracks = [p.track(track_id)] if track_id else list(p.tracks)
    hits = [c for tr in tracks for c in tr.clips if c.start <= start < c.end]
    if not hits:
        raise CandidateError("error.candidates.no_clip", frame=start)
    clip = min(hits, key=lambda c: c.muted)
    end = min(end, clip.end)
    a = frames_to_flicks(clip.offset + start - clip.start, p.rate)
    b = frames_to_flicks(clip.offset + end - clip.start, p.rate)
    anchor, scope = clip.media, "track"
    found = p.sync_member(clip.media)
    if found is not None:
        group, origin = found
        main = p.sync_member(group.main)
        if main is not None:
            anchor, scope = group.main, "group"
            a, b = a + origin - main[1], b + origin - main[1]
    return Candidate(id=candidate_id(_sha(p, anchor), "marked", a, b), kind="marked",
                     media=anchor, start=a, end=b, scope=scope, score=SCORE_MARKED,
                     reason={"key": "candidate.reason.marked", "params": {}})


def apply_plan(p: Project, c: Candidate, tracks: Iterable[str] | None = None,
               mode: str = "soft") -> Plan:
    """What accepting ``c`` does, without doing it.

    ``soft`` (the default; Delete) mutes the candidate in place with
    ``ops.mute_range`` and leaves the gap. ``ripple`` (Cut) removes it with
    ``ops.cut_range``, last span first so the earlier ones stay where they
    are. ``tracks``: where to apply (default: the tracks that play the
    candidate's recording). The track set is widened by WP19a's rule
    (``edit_scope.expand_range``): a group candidate covers its whole sync
    group, and a ripple always keeps a group together and moves tracks in no
    group with it, so nothing slips out of step.
    """
    if mode not in MODES:
        raise CandidateError("error.candidates.bad_mode", mode=mode)
    pieces = place(p, c)
    cut = _union((x.start, x.end) for x in pieces)
    if not cut:
        raise CandidateError("error.candidates.not_placed", id=c.id)
    order = [tr.id for tr in p.tracks]
    base = (list(dict.fromkeys(tracks)) if tracks is not None
            else sorted({x.track for x in pieces}, key=order.index))
    out, touched = p, set()
    for a, b in reversed(cut):
        if mode == "soft":
            scope = edit_scope.expand_range(out, None, base, a, b, c.scope == "group")
            out = ops.mute_range(out, a, b, scope)
        else:
            scope = edit_scope.expand_range(out, None, base, a, b, True)
            out = ops.cut_range(out, a, b, scope)
        touched.update(scope)
    pad = round(PREVIEW_PAD_S * p.rate)
    preview = {"from": max(0, cut[0][0] - pad), "to": cut[-1][1] + pad,
               "skip": [[a, b] for a, b in cut]}
    return Plan(mode=mode, spans=tuple(cut),
                tracks=tuple(tid for tid in order if tid in touched),
                project=out, preview=preview)


def reason_text(c: Candidate) -> str:
    """The reason in the current language ("Pause 3,0 s")."""
    params = c.reason.get("params") or {}
    if c.kind == "silence":
        seconds = f"{float(params.get('seconds', 0)):.1f}"
        if language() == "fi":
            seconds = seconds.replace(".", ",")
        return t("candidate.reason.silence", seconds=seconds)
    if c.kind == "filler":
        return t("candidate.reason.filler", word=params.get("word", c.text))
    if c.kind == "retake":
        return t("candidate.reason.retake", text=params.get("text", c.text))
    if c.kind == "breath":
        return t("candidate.reason.breath")
    return t("candidate.reason.marked")
