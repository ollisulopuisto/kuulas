"""One open project: the only place History, MediaStore and ops meet (WP1).

A ``Session`` opens (or creates) a ``Name.kuulas`` package (``package``) and
turns every change into exactly one ``History.commit`` before it returns, so
nothing the user did lives only in memory. Callers (the HTTP API, the
playback engine) never touch ``History`` or ``ops`` directly.

Every public method holds ``lock`` (re-entrant): the API serves requests on
several threads and the engine reads ``state`` from another, and a commit is
a read-modify-write of the history head.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from . import analysis, ops, package, transcript
from .clock import flicks_to_frames
from .history import History
from .media import ImportResult, MediaError, MediaStore
from .messages import t
from .model import Project, SyncGroup

log = logging.getLogger("kuulas.session")

#: Edit names whose clicks coalesce (WP24.1): one key for solo, so clicking
#: through the tracks to listen to each is one undo step, not twenty...
SOLO_KEY = "solo"
#: ...and mute/unmute clicks on one track merge with each other, not with
#: those on another track.
MUTE_FIELDS = {"mute", "solo"}

#: How many selected words a "cut" label quotes before it stops.
LABEL_WORDS = 5


def _sync_partners(groups: tuple[SyncGroup, ...]) -> dict[str, tuple[str, ...]]:
    """Media id -> the other media that ran on the same clock."""
    out: dict[str, tuple[str, ...]] = {}
    for g in groups:
        ids = sorted(m for m, _ in g.members)
        for m in ids:
            out[m] = tuple(o for o in ids if o != m)
    return out


def _coalesce_key(name: str, args: dict) -> str | None:
    if name == "solo":
        return SOLO_KEY
    switches = set(args) - {"track_id"}
    if name == "set_track" and args.get("track_id") and switches <= MUTE_FIELDS:
        return f"mute:{args['track_id']}"
    return None


class Session:
    """``folder`` is the ``Name.kuulas`` package; it is created if it does not
    exist. ``rate`` applies to a new project only: an existing one keeps its own."""

    def __init__(self, folder: str | Path, rate: int = 48000):
        folder = Path(folder)
        self.lock = threading.RLock()
        if (folder / "manifest.json").exists() or (folder / "project.sqlite").exists():
            self.package = package.open_package(folder)
        else:
            self.package = package.create(folder, rate)
        self.package.start()
        self.history: History = self.package.history
        self.store: MediaStore = self.package.store
        self._subscribers: list[Callable[[Project], None]] = []
        #: What became of each file in the latest import (WP34), for the UI
        #: to show: the failures and why, and the warnings of those that came in.
        self.last_import_report: list[ImportResult] = []

    # -- the project -------------------------------------------------------

    @property
    def state(self) -> Project:
        with self.lock:
            return self.history.state

    @property
    def read_only(self) -> bool:
        return self.package.read_only

    def close(self) -> None:
        with self.lock:
            self.history.budget.log_stats()
            self.package.close()

    def subscribe(self, fn: Callable[[Project], None]) -> None:
        """Call ``fn(state)`` after every change to the project, undo and redo
        included. A subscriber that raises is logged and skipped: the change
        is already on disk and the others still need to hear of it."""
        with self.lock:
            self._subscribers.append(fn)

    def _changed(self) -> Project:
        state = self.history.state
        for fn in list(self._subscribers):
            try:
                fn(state)
            except Exception:  # one broken listener must not stop the rest
                log.exception(t("log.session.subscriber_failed"))
        return state

    # -- edits -------------------------------------------------------------

    def edit(self, name: str, args: dict, label: str | None = None,
             coalesce: str | None = None) -> Project:
        """Apply the named op (``ops.OPS``) and commit it as one undo step.

        Solo and mute clicks coalesce by themselves (``_coalesce_key``); pass
        ``coalesce`` to choose another run, such as a slider drag.
        """
        with self.lock:
            new = ops.apply(self.history.state, name, args)
            self.history.commit(label or name, new,
                                coalesce or _coalesce_key(name, args),
                                op={"name": name, "args": args})
            return self._changed()

    def command(self, name: str, args: dict) -> Project:
        """An edit that needs more than the project: the media store, the
        transcript. See ``COMMANDS``."""
        with self.lock:
            try:
                run = COMMANDS[name]
            except KeyError:
                raise ops.EditError("error.edit.unknown", name=name) from None
            return run(self, args)

    def _commit(self, label: str, new: Project, name: str, args: dict) -> Project:
        self.history.commit(label, new, op={"name": name, "args": args})
        return self._changed()

    # -- history -----------------------------------------------------------

    def undo(self) -> bool:
        with self.lock:
            moved = self.history.undo()
            if moved:
                self._changed()
            return moved

    def redo(self) -> bool:
        with self.lock:
            moved = self.history.redo()
            if moved:
                self._changed()
            return moved

    def goto(self, node: str) -> None:
        """Restore the project to any step, on any branch. Nothing is lost:
        the steps left behind stay reachable."""
        with self.lock:
            self.history.goto(node)
            self._changed()

    def restore(self, node: str) -> Project:
        """Make the project equal to any step by adding a step (WP8's
        ledger-style restore); Undo returns to where you were."""
        with self.lock:
            self.history.restore(node)
            return self._changed()

    def checkpoint(self, name: str, kind: str = "manual") -> None:
        """Name the current step ("v1 sent to Ville"). Not an edit."""
        with self.lock:
            self.history.checkpoint(name, kind)

    # -- import ------------------------------------------------------------

    def import_media(self, paths: list[str], copy: bool = False,
                     track_per_file: bool = True) -> Project:
        """``import_media_report`` without the report (it stays in
        ``last_import_report``). Raises if not one file could be imported."""
        return self.import_media_report(paths, copy, track_per_file)[0]

    def import_media_report(self, paths: list[str], copy: bool = False,
                            track_per_file: bool = True,
                            ) -> tuple[Project, list[ImportResult]]:
        """Bring files in and put them on the timeline, as ONE undo step.

        Fail soft (WP34): a file that cannot be imported is left out and
        named in the report with the reason; the others still come in. Only
        when none can does this raise (that file's own error if it was the
        only one), and then nothing changes.

        One new track per file, with one clip at the start; stereo is music,
        mono is speech. Files imported together were recorded together, so
        they are one sync group, placed by their recorders' clocks (BWF time
        reference, relative to the earliest; a file without one starts at 0).
        A file that does not belong (a Zoom or phone recording) is aligned
        by hand and marked in sync later. ``track_per_file=False`` puts the
        files one after another on a single track instead; that is not the
        same moment, so no group.
        """
        with self.lock:
            report = self.store.import_batch(paths, copy)
            self.last_import_report = report
            ok = [(str(x), r) for x, r in zip(paths, report, strict=True) if r.ok]
            if report and not ok:
                if len(report) == 1:
                    raise report[0].error
                raise MediaError("error.media.all_failed", count=len(report),
                                 details=" ".join(str(r.error) for r in report))
            media = [r.media for _, r in ok]
            p = self.history.state
            refs = [m.time_ref_flicks for m in media]
            earliest = min((r for r in refs if r is not None), default=0)
            clip_ids: list[str] = []
            if track_per_file:
                for m in media:
                    track_id, clip_id = ops.new_id("t"), ops.new_id("c")
                    start = (0 if m.time_ref_flicks is None
                             else flicks_to_frames(m.time_ref_flicks - earliest, p.rate))
                    p = ops.add_track(p, track_id, Path(m.name).stem,
                                      "music" if m.channels >= 2 else "speech")
                    p = ops.add_clip(p, track_id, m.id, start=start, clip_id=clip_id)
                    clip_ids.append(clip_id)
            elif media:
                track_id, start = ops.new_id("t"), 0
                p = ops.add_track(p, track_id, Path(media[0].name).stem,
                                  "music" if media[0].channels >= 2 else "speech")
                for m in media:
                    p = ops.add_clip(p, track_id, m.id, start=start)
                    start += m.frames
            if track_per_file and len({m.id for m in media}) > 1:
                # Exact clocks when every file has one (or none does); mixed,
                # the files that have none were placed at 0, so the placement
                # on the timeline is what the group has to say.
                basis = "files" if len({r is None for r in refs}) == 1 else "timeline"
                p = ops.mark_in_sync(p, clip_ids, main=clip_ids[0], basis=basis)
            label = t("history.import", count=len(media))
            # Only what came in is recorded: replaying the step must not
            # depend on files that failed.
            return (self._commit(label, p, "import_media",
                                 {"paths": [x for x, _ in ok], "copy": copy,
                                  "track_per_file": track_per_file}), report)

    # -- transcripts -------------------------------------------------------

    def transcripts(self) -> dict[str, list[dict]]:
        """Media id -> its words (flicks from the media's start), as the
        material says they are now. A revision is read once and kept."""
        with self.lock:
            out = {}
            for media_id, stored in self.history.material["transcripts"].items():
                rev = int(stored)
                # A revision never changes once stored, so it is kept (in the
                # memory budget) for as long as there is room for it.
                out[media_id] = self._memo(
                    "words", self._view_key(rev),
                    lambda rev=rev: self.history.transcript(rev), 150)
            return out

    def set_transcript(self, media_id: str, words: list[dict], label: str) -> Project:
        """A new transcript for one media: one step, undone with Undo."""
        with self.lock:
            try:
                self.history.state.media_item(media_id)
            except KeyError:
                raise ops.EditError("error.edit.no_media", media_id=media_id) from None
            self.history.add_transcript(media_id, words, label=label)
            return self._changed()

    def correct_word(self, media_id: str, index: int, text: str) -> Project:
        """Correct the text of one word of one media's transcript: a new
        transcript revision, one undo step. Its timing and speaker stay."""
        with self.lock:
            words = list(self.transcripts().get(media_id, ()))
            if not 0 <= index < len(words):
                raise ops.EditError("error.edit.no_word", media_id=media_id,
                                    index=index, count=len(words))
            old = words[index]["w"]
            words[index] = {**words[index], "w": text.strip()}
            return self.set_transcript(
                media_id, words, t("history.correct_word", old=old, new=text.strip()))

    def _view_key(self, *parts: object) -> str:
        """Key of a memoized view: this project, and what the view is of."""
        return "|".join((str(self.history.path), *map(str, parts)))

    def timeline_words(self) -> list[dict]:
        """Every word the timeline plays, memoized on (edit state, rate,
        transcript revisions): the same state asked twice, or reached again
        by undo, costs nothing. The list is yours; the word dicts in it are
        shared and must not be changed."""
        with self.lock:
            revs = sorted(self.history.material["transcripts"].items())
            key = self._view_key(self.history.edit_hash, self.history.rate, revs)

            def compute() -> list[dict]:
                return transcript.timeline_words(self.history.state, self.transcripts())

            return list(self._memo("timeline_words", key, compute, 300))

    def sync_partners(self) -> dict[str, tuple[str, ...]]:
        """Media id -> the media recorded on the same clock, memoized on the
        material revision (sync groups are material)."""
        with self.lock:
            key = self._view_key(self.history.material_head)
            return dict(self._memo(
                "sync_partners", key,
                lambda: _sync_partners(self.history.state.sync_groups), 100))

    def _memo(self, name: str, key: str, compute: Callable[[], object],
              bytes_per_item: int):
        """``compute()`` once per ``key``, in the shared memory budget."""
        budget = self.history.budget
        value = budget.get(name, key)
        if value is None:
            value = compute()
            budget.put(name, key, value, 1024 + bytes_per_item * len(value))
        return value


# -- commands ----------------------------------------------------------------


def _auto_silence(s: Session, args: dict) -> Project:
    new = analysis.auto_silence(s.history.state, s.store, args.get("track_ids"))
    return s._commit(t("history.auto_silence"), new, "auto_silence", args)


def _automix(s: Session, args: dict) -> Project:
    kwargs = {} if "depth_db" not in args else {"depth_db": float(args["depth_db"])}
    new = analysis.automix(s.history.state, s.store, **kwargs)
    return s._commit(t("history.automix"), new, "automix", args)


def _cut_words(s: Session, args: dict) -> Project:
    """Delete words from the audio: the stretch they cover is ripple-deleted
    on every track, so the speakers stay together."""
    words = s.timeline_words()
    chosen = sorted({int(i) for i in args.get("indices", ())})
    if not chosen:
        raise ops.EditError("error.edit.no_selection")
    if chosen[0] < 0 or chosen[-1] >= len(words):
        raise ops.EditError("error.session.bad_word_index", index=chosen[-1],
                            count=len(words))
    start, end = transcript.cut_range(words, chosen)
    new = ops.ripple_delete(s.history.state, start, end)
    quoted = " ".join(words[i]["w"] for i in chosen[:LABEL_WORDS])
    if len(chosen) > LABEL_WORDS:
        quoted += "…"
    return s._commit(t("history.cut_words", text=quoted), new, "cut_words", args)


def _relink(s: Session, args: dict) -> Project:
    """Find moved media again by content. Not an edit: the project is the same."""
    found = s.store.relink(args.get("folder"))
    log.info(t("log.session.relinked", count=len(found)))
    return s.history.state


def _consolidate(s: Session, _args: dict) -> Project:
    """Copy linked media into the project. Not an edit: the project is the same."""
    done = s.store.consolidate()
    log.info(t("log.session.consolidated", count=len(done)))
    return s.history.state


#: Name -> function(session, args) -> Project. The session lock is held.
#: ``auto_silence``, ``automix`` and ``cut_words`` commit one step each;
#: ``relink`` and ``consolidate`` change no state and commit nothing.
COMMANDS: dict[str, Callable[[Session, dict], Project]] = {
    "auto_silence": _auto_silence,
    "automix": _automix,
    "cut_words": _cut_words,
    "relink": _relink,
    "consolidate": _consolidate,
}
