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

import contextlib
import json
import logging
import math
import os
import sqlite3
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from lxml import etree
from nhsx import NhsxError
from nhsx import locate as nhsx_locate
from nhsx import read as read_nhsx
from nhsx import tracks as nhsx_tracks
from nhsx.mix import level_at as nhsx_level_at
from nhsx.mix import plan as nhsx_mix_plan
from nhsx.read import children as nhsx_children
from nhsx.read import descendants as nhsx_descendants
from nhsx.read import localname as nhsx_localname
from nhsx.read import time_to_seconds as nhsx_time_to_seconds

from . import (
    analysis,
    candidates,
    clipboard_link,
    collateral,
    edit_points,
    edit_scope,
    import_plan,
    narration,
    narration_script,
    onsets,
    ops,
    package,
    source_map,
    subtitles,
    transcribe,
    transcript,
    transcript_text,
)
from . import chapters as chapters_module
from . import db as dbm
from . import export as export_module
from . import loudness_curve as loudness_curve_module
from . import markers as markers_module
from . import music_report as music_report_module
from .clipboard import ClipRef, Entry, entry_from_refs, make_entry, make_entry_range
from .clipboard_preview import preview_project
from .clipboard_store import ClipboardStore, entry_dict
from .clock import FLICKS, frames_to_flicks
from .history import History, UndoInfo
from .jobs import JobCancelledError, Jobs
from .loudness import gain_to_target, measure_clip, track_target_lufs
from .media import ImportResult, MediaError, MediaStore
from .messages import KuulasError, t
from .model import Project, SyncGroup
from .paste_apply import apply_paste
from .paste_plan import _targets, plan_paste
from .people import Interview, Passage, Person

log = logging.getLogger("kuulas.session")


class NhsxImportError(KuulasError, ValueError):
    """A Hindenburg session could not be parsed or mapped safely."""


class NoSuchEntryError(ops.EditError):
    """The clipboard has no entry with that id (the API answers 404)."""


class SubtitlesError(ops.EditError):
    """Unknown subtitle format."""


class NarrationScriptError(ops.EditError):
    """The narration script was asked for in a format that does not exist."""


class TranscriptTextError(ops.EditError):
    """Unknown transcript text format."""


class MatchReport(dict):
    """Report from match_loudness: matched (clip_id, measured, new_gain) and skipped."""

    @property
    def matched(self) -> list[tuple[str, float, float]]:
        return self["matched"]

    @property
    def skipped(self) -> list[str]:
        return self["skipped"]

    def __iter__(self):
        return iter((self["matched"], self["skipped"]))


#: The edit names ``/api/edit`` hands to ``Session.clipboard_edit``: they are
#: edits with a clipboard side, which ``ops`` (pure, project-only) cannot be.
CLIPBOARD_EDITS = ("clipboard_cut", "clipboard_lift_cut", "clipboard_paste")


def _db_value(value: str | None) -> float:
    try:
        result = float(value) if value is not None else 0.0
    except ValueError:
        return 0.0
    return result if math.isfinite(result) else 0.0


def _time_value(value: str | None) -> float:
    try:
        return max(0.0, nhsx_time_to_seconds(value))
    except ValueError:
        return 0.0


def _truth(value: str | None) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes"}


def _region_levels(elem, rate: int) -> dict:
    """The gain, pan, fades and mute a Hindenburg region element carries, in
    the keyword names clips and clipboard references share."""
    clip_gain = elem.get("ClipGain")
    gain = _db_value(clip_gain) if clip_gain is not None else _db_value(elem.get("Gain"))
    return {"gain_db": gain,
            "pan": max(-1.0, min(1.0, _db_value(elem.get("Pan")))),
            "fade_in": round(_time_value(elem.get("FadeIn")) * rate),
            "fade_out": round(_time_value(elem.get("FadeOut")) * rate),
            "muted": _truth(elem.get("Muted"))}


def _nhsx_clipboard_clips(root) -> list[tuple[int, Any]]:
    """``(clipboard number, Clip element)`` for every clip in the session's
    ``<Clipboard>``; the number counts groups from 1, empty ones included."""
    out = []
    for board in nhsx_children(root, "Clipboard"):
        for number, group in enumerate(
                (g for g in board if nhsx_localname(g) == "Group"), start=1):
            out.extend((number, clip) for clip in nhsx_children(group, "Clip"))
    return out


def _element_xml(elem) -> str:
    if elem is None:
        return ""
    return etree.tostring(elem, encoding="unicode", with_tail=False)


def _ramp_points(ramps, offset: float, rate: int) -> tuple[tuple[int, float], ...]:
    """Sample nhsx's raised-cosine ramps for kuulas's source-clock envelope."""
    if not ramps:
        return ()
    points = {}
    for ramp in ramps:
        steps = max(2, math.ceil(ramp.length * 50))
        for index in range(steps + 1):
            when = ramp.start + ramp.length * index / steps
            level = max(1e-6, nhsx_level_at(ramps, when))
            frame = round((offset + when) * rate)
            points[frame] = 20 * math.log10(level)
    return tuple(sorted(points.items()))


def _nhsx_words(file_info) -> list[dict]:
    node = file_info.transcription
    if node is None:
        return []
    words = []
    for elem in nhsx_descendants(node, "w"):
        text = (elem.text or "").strip()
        if not text:
            continue
        try:
            start = round(nhsx_time_to_seconds(elem.get("s")) * FLICKS)
            length = round(nhsx_time_to_seconds(elem.get("l")) * FLICKS)
        except ValueError:
            continue
        words.append({"w": text, "s": start, "e": max(start + 1, start + length),
                      "spk": elem.get("sp", "")})
    return words

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

    def __init__(self, folder: str | Path, rate: int = 48000,
                 clipboard: ClipboardStore | None = None):
        folder = Path(folder)
        #: The per-user clipboard history (WP46), shared by every project and
        #: every kuulas window of this user.
        self.clipboard = clipboard or ClipboardStore()
        self.lock = threading.RLock()
        if (folder / "manifest.json").exists() or (folder / "project.sqlite").exists():
            self.package = package.open_package(folder)
            is_new = False
        else:
            self.package = package.create(folder, rate)
            is_new = True
        self.package.start()
        self.jobs = Jobs()
        #: Folder of the last "Export all tracks" this run made, for Show in Finder.
        self.last_export_folder: str | None = None
        self.history: History = self.package.history
        self.store: MediaStore = self.package.store
        self._subscribers: list[Callable[[Project], None]] = []
        #: What became of each file in the latest import (WP34), for the UI
        #: to show: the failures and why, and the warnings of those that came in.
        self.last_import_report: list[ImportResult] = []
        #: How many Hindenburg clipboard clips the last ``import_nhsx`` turned
        #: into clipboard entries.
        self.last_import_clipboard = 0
        #: The interview the latest import made (WP41), or None.
        self.last_import_interview: str | None = None
        #: New stereo speech tracks of the latest import, ``[{id, name}]``: the
        #: UI asks whether to turn them into mono.
        self.last_import_stereo: list[dict] = []
        #: The report from the latest match_loudness command (WP19c).
        self.last_backup: Path | None = None  # the newest save_backup (Mod+S)
        self.last_match_report: MatchReport = MatchReport({"matched": [], "skipped": []})
        if not is_new and not self.read_only:
            self.history.session_opened()

    # -- the project -------------------------------------------------------

    @property
    def state(self) -> Project:
        with self.lock:
            return self.history.state

    @property
    def read_only(self) -> bool:
        return self.package.read_only

    def close(self) -> None:
        self.jobs.close()
        with self.lock:
            if not self.read_only:
                with contextlib.suppress(sqlite3.Error, KuulasError, OSError):
                    self.history.session_closed()
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

    def command(self, name: str, args: dict | None = None) -> Project:
        """An edit that needs more than the project: the media store, the
        transcript. See ``COMMANDS``. Those in ``LOCK_FREE_COMMANDS`` take the
        lock themselves, only for their snapshot and their commit."""
        if args is None:
            args = {}
        try:
            run = COMMANDS[name]
        except KeyError:
            raise ops.EditError("error.edit.unknown", name=name) from None
        if name in LOCK_FREE_COMMANDS:
            return run(self, args)
        with self.lock:
            return run(self, args)

    def duck_music(self) -> Project:
        return self.command("duck_music")

    def match_loudness(self, clip_ids: list[str],
                       target_lufs: float | None = None) -> Project:
        """Set each clip's gain_db so its loudness matches target_lufs (WP19c).

        Measuring runs outside the session lock in a thread pool of at most 4 workers.
        Commits ONE undoable step with all updated clip gains.
        Silent clips (quieter than -70 LUFS or too short) are skipped.
        Remembers MatchReport in ``last_match_report``.
        """
        if target_lufs is not None:
            target_lufs = float(target_lufs)
        with self.lock:
            state = self.history.state
            initial_head = self.history.head
            clips_to_measure = []
            targets: dict[str, float | None] = {}
            mono: dict[str, bool] = {}
            for cid in clip_ids:
                try:
                    clip, track = state.clip_and_track(cid)
                    clips_to_measure.append(clip)
                    mono[cid] = track.mono  # a mono track is measured as heard
                    # An explicit target wins; else the track's own, else its role's.
                    targets[cid] = (target_lufs if target_lufs is not None
                                    else track_target_lufs(track))
                except KeyError:
                    raise ops.EditError("error.edit.no_clip", clip_id=cid) from None

        max_workers = min(4, max(1, len(clips_to_measure)))

        def _measure(clip):
            val = measure_clip(self.store, clip, state.rate, mono=mono[clip.id])
            return clip.id, val

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            measured_results = list(executor.map(_measure, clips_to_measure))

        matched: list[tuple[str, float, float]] = []
        skipped: list[str] = []
        new_gains: dict[str, float] = {}

        for cid, measured in measured_results:
            if measured is None:
                skipped.append(cid)
                continue
            new_gain = gain_to_target(measured, targets[cid])
            if new_gain is None:
                skipped.append(cid)
                continue
            matched.append((cid, measured, new_gain))
            new_gains[cid] = new_gain

        with self.lock:
            if self.history.head != initial_head:
                raise ops.EditError("error.session.concurrent_edit")

            new_state = self.history.state
            for cid, g in new_gains.items():
                new_state = ops.set_clip(new_state, cid, gain_db=g)

            self.last_match_report = MatchReport({
                "matched": matched,
                "skipped": skipped,
            })
            args = {"clip_ids": list(clip_ids), "target_lufs": target_lufs}
            return self._commit(
                t("history.match_loudness"), new_state, "match_loudness", args
            )

    def _commit(self, label: str, new: Project, name: str, args: dict,
                material: dict | None = None) -> Project:
        self.history.commit(label, new, op={"name": name, "args": args},
                            material=material)
        return self._changed()

    def _material_step(self, label: str, root: dict, name: str, args: dict) -> None:
        """One undo step that changes only material (people, interviews, maps)."""
        self.history.set_material(label, root, op={"name": name, "args": args})
        self._changed()

    # -- the clipboard (WP46) -----------------------------------------------
    #
    # The history file is read and written outside ``lock``: a slow disk must
    # not stall playback's reads of ``state``. Under the lock a command takes
    # the project snapshot and commits; everything else works on the snapshot.

    def _entry_view(self, entry: Entry, project: Project) -> dict:
        have = {m.sha256 for m in project.media}
        wanted = {ref.media_sha256 for ref in entry.refs}
        return {**entry_dict(entry), "length": entry.span[1] - entry.span[0],
                "clips": len(entry.refs),
                "slots": len({ref.track_slot for ref in entry.refs}),
                "missing_here": len(wanted - have),
                "source_name": Path(entry.source_project).stem}

    def _entry(self, entry_id: str) -> Entry:
        entry = self.clipboard.load().get(entry_id)
        if entry is None:
            raise NoSuchEntryError("error.clipboard.no_entry", entry_id=entry_id)
        return entry

    def clipboard_list(self) -> list[dict]:
        """The history, newest first, each entry with what the panel shows:
        its length, clip and track counts and how many of its recordings this
        project lacks."""
        project = self.state
        return [self._entry_view(e, project) for e in self.clipboard.load().entries()]

    def clipboard_preview(self, entry_id: str):
        """``(temporary project or None, missing media count)`` for playing an
        entry without changing this project (``clipboard_preview``)."""
        project, missing = preview_project(self.state, self._entry(entry_id))
        return project, len(missing)

    def clipboard_copy(self, *, clip_ids=None, start=None, end=None, track_ids=None,
                       group_editing: bool = False, name: str = "") -> dict:
        """Copy the clips, or the stretch ``[start, end)`` of the tracks, to the
        clipboard; ``group_editing`` takes the tracks' sync groups along, as a
        Cut of the same range would. The project is not changed."""
        project = self.state
        if clip_ids is not None:
            entry = make_entry(project, clip_ids, name=name)
        elif start is None or end is None:
            raise ops.EditError("error.edit.no_selection")
        else:
            if track_ids is not None:
                track_ids = edit_scope.expand_range(project, None, list(track_ids),
                                                    int(start), int(end),
                                                    bool(group_editing))
            entry = make_entry_range(project, int(start), int(end), track_ids, name=name)
        entry = replace(entry, source_project=str(self.package.path))
        self.clipboard.update(lambda h: h.add(entry))
        return {"entry": self._entry_view(entry, project)}

    def clipboard_cut(self, *, start: int, end: int, track_ids,
                      group_editing: bool = False, name: str = "",
                      label: str | None = None) -> dict:
        """Cut (X): ripple-delete ``[start, end)`` and keep what went on the
        clipboard. One undo step for the removal. A copy that fails (nothing
        under the range, a full disk) is logged and reported in the result, and
        never stops the cut: the user's edit comes first."""
        return self._cut_to_clipboard("clipboard_cut", ops.cut_range, start=start,
                                      end=end, track_ids=track_ids,
                                      group_editing=group_editing, name=name,
                                      label=label or t("history.clipboard_cut"))

    def clipboard_lift_cut(self, *, start: int, end: int, track_ids,
                           group_editing: bool = False, name: str = "",
                           label: str | None = None) -> dict:
        """Lift-cut (Alt+X): copy ``[start, end)`` to the clipboard and soft-delete
        it in place (the gap stays, restorable). Same targets, one undo step and
        failure rule as ``clipboard_cut``."""
        return self._cut_to_clipboard("clipboard_lift_cut", ops.mute_range, start=start,
                                      end=end, track_ids=track_ids,
                                      group_editing=group_editing, name=name,
                                      label=label or t("history.clipboard_lift_cut"))

    def _cut_to_clipboard(self, op_name: str, remove: Callable, *, start: int, end: int,
                          track_ids, group_editing: bool, name: str,
                          label: str) -> dict:
        start, end = int(start), int(end)
        with self.lock:
            project = self.history.state
            scope = edit_scope.expand_range(project, None, list(track_ids), start, end,
                                            bool(group_editing))
            entry, problem = None, None
            try:
                entry = replace(make_entry_range(project, start, end, scope, name=name),
                                source_project=str(self.package.path))
            except KuulasError as e:
                problem = t(e.key, **e.params)
            new = remove(project, start, end, track_ids, bool(group_editing))
            self.history.commit(label, new,
                                op={"name": op_name,
                                    "args": {"start": start, "end": end,
                                             "track_ids": list(track_ids),
                                             "group_editing": bool(group_editing)}})
            self._changed()
        if entry is not None:
            try:
                self.clipboard.update(lambda h, e=entry: h.add(e))
            except OSError as e:
                problem = t("error.clipboard.write_failed", error=str(e))
        if problem is not None:
            log.warning(t("log.clipboard.copy_failed", error=problem))
            return {"clipboard": {"ok": False, "entry": None, "error": problem}}
        return {"clipboard": {"ok": True, "entry": entry.id, "error": None}}

    def _link_missing_media(self, entry: Entry) -> None:
        """Pasting into another project: link, in place and without copying,
        the recordings this project lacks from the files the entry's source
        project imported them from, when such a file is still there and still
        has the hash. What cannot be found stays missing (reported by the
        paste). Media are material shared by every edit, so linking is not an
        undo step of its own; the paste after it is."""
        here = Path(self.package.path)
        if not entry.source_project or Path(entry.source_project) == here:
            return
        have = {m.sha256 for m in self.state.media}
        for digest in sorted({r.media_sha256 for r in entry.refs} - have):
            for path in clipboard_link.candidate_paths(entry.source_project, digest):
                if not clipboard_link.has_digest(path, digest):
                    continue
                result = self.store.import_batch([path], copy=False)[0]
                if result.ok:
                    break

    def clipboard_paste(self, entry_id: str, *, at: int, mode: str = "insert",
                        target_tracks=None, group_editing: bool = True,
                        label: str | None = None) -> dict:
        """Paste an entry at frame ``at`` as one undo step; ``mode`` is
        ``insert`` (ripple) or ``overwrite``. ``target_tracks`` maps the
        entry's track slots to track ids (``None``: the same tracks). Media
        the project lacks are reported in ``missing`` and their clips left
        out; a paste that places nothing commits nothing. An insert is a
        time-shifting edit (WP19a): with ``group_editing`` (the default) it
        ripples every track ``edit_scope.expand_range`` names for the target
        tracks, so a sync group stays in step; the tracks that only shift get
        no clips."""
        entry = self._entry(entry_id)
        self._link_missing_media(entry)
        mapping = (None if target_tracks is None
                   else {int(slot): track for slot, track in target_tracks.items()})
        at = int(at)
        with self.lock:
            project = self.history.state
            plan = plan_paste(project, entry, at, mode, mapping)
            report = {"placed": len(plan.placements), "missing": list(plan.missing),
                      "entry": entry.id}
            if not plan.placements:
                return report
            landed = set(_targets(project, entry, mapping).values())
            if mode == "insert":
                landed |= set(edit_scope.expand_range(
                    project, None, sorted(landed), at, at + plan.shift,
                    bool(group_editing)))
            new = apply_paste(project, entry, plan, at, landed, mode)
            self.history.commit(
                label or t("history.clipboard_paste"), new,
                op={"name": "clipboard_paste",
                    "args": {"entry_id": entry.id, "at": at, "mode": mode,
                             "target_tracks": target_tracks,
                             "group_editing": bool(group_editing)}})
            self._changed()
        return report

    def clipboard_edit(self, op: str, args: dict, label: str | None = None) -> dict:
        """``/api/edit``'s door to the edits that touch the clipboard."""
        try:
            if op == "clipboard_cut":
                return self.clipboard_cut(**args, label=label)["clipboard"]
            if op == "clipboard_lift_cut":
                return self.clipboard_lift_cut(**args, label=label)["clipboard"]
            if op == "clipboard_paste":
                return self.clipboard_paste(**args, label=label)
        except TypeError as e:
            raise ops.EditError("error.edit.bad_arguments", name=op,
                                detail=str(e)) from None
        raise ops.EditError("error.edit.unknown", name=op)

    def _change_history(self, entry_id: str, change: Callable) -> None:
        def run(history):
            if history.get(entry_id) is None:
                raise NoSuchEntryError("error.clipboard.no_entry", entry_id=entry_id)
            change(history)

        self.clipboard.update(run)

    def clipboard_pin(self, entry_id: str, pinned: bool = True) -> None:
        self._change_history(entry_id, lambda h: h.pin(entry_id) if pinned
                             else h.unpin(entry_id))

    def clipboard_rename(self, entry_id: str, name: str) -> None:
        clean = str(name).strip()[:200]
        self._change_history(entry_id, lambda h: h.rename(entry_id, clean))

    def clipboard_delete(self, entry_id: str) -> None:
        self._change_history(entry_id, lambda h: h.delete(entry_id))

    # -- history -----------------------------------------------------------

    def undo(self) -> UndoInfo | None:
        with self.lock:
            moved = self.history.undo()
            if moved:
                self._changed()
            return moved

    def redo(self) -> UndoInfo | None:
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

    def export(self, args: dict, *, progress=None, cancel=None,
               workers: int | None = None) -> dict:
        """Render a mix, selection or track stems without changing the edit."""
        return export_module.run(self, args, progress, cancel, workers)

    def chapters(self, style: str = "text") -> str:
        """The chapter markers as a chapter list: ``"text"`` (``hh:mm:ss
        Title`` per line) or ``"json"`` (Podcasting 2.0). The snapshot is taken
        under the lock; the text is built outside it."""
        with self.lock:
            state = self.history.state
        return chapters_module.format_chapters(
            markers_module.chapters(state.markers), state.rate, style)

    def export_regions(self, args: dict) -> list[str]:
        """Queue ONE job that renders every region (marker kind ``region``) to
        its own file with the selection export. Checked now, rendered in the
        background; answers the job id in a list, like ``transcribe``."""
        plan, settings = export_module.plan_regions(self, args)
        title = t("job.export_regions", count=len(plan))

        def run(progress):
            try:
                return export_module.run_regions(
                    self, plan, settings, lambda fraction, _message: progress(fraction),
                    progress.cancelled_event)
            except export_module.ExportError:
                if progress.cancelled:
                    raise JobCancelledError from None
                raise

        return [self.jobs.submit("export", title, run)]

    def tracks_export_args(self, args: dict | None = None) -> dict:
        """The export arguments of the one-button track export: ``export.ALL_TRACKS``
        (the folder is ``<project> exports`` beside the project) and any
        ``format``, ``bit_depth`` or ``folder`` the caller chose. Each run gets
        its own folder (the template carries the time), so nothing is overwritten."""
        chosen = {k: v for k, v in (args or {}).items()
                  if k in {"format", "bit_depth", "kbps", "folder"} and v is not None}
        return {**export_module.ALL_TRACKS, **chosen}

    def mix_export_args(self, args: dict | None = None) -> dict:
        """The export arguments of the one-button mix export: ``export.MIX_FILE``
        (a file in ``<project> exports`` named by edit, time and version) and any
        ``format``, ``bit_depth``, ``kbps`` or ``folder`` the caller chose."""
        chosen = {k: v for k, v in (args or {}).items()
                  if k in {"format", "bit_depth", "kbps", "folder"} and v is not None}
        return {**export_module.MIX_FILE, **chosen}

    def _export_job(self, export_args: dict, title: str) -> list[str]:
        """Queue ONE export as a background job. Bad settings and a read-only
        project fail now. ``last_export_folder`` becomes where it went."""
        export_module.check(self, export_args)

        def run(progress):
            try:
                result = export_module.run(
                    self, export_args, lambda fraction, _message: progress(fraction),
                    progress.cancelled_event)
            except export_module.ExportError:
                if progress.cancelled:
                    raise JobCancelledError from None
                raise
            path = Path(result["path"])
            self.last_export_folder = str(path if path.is_dir() else path.parent)
            return result

        return [self.jobs.submit("export", title, run, keep_result=True)]

    def export_tracks(self, args: dict | None = None) -> list[str]:
        """Queue ONE job that exports every track as a file (see
        ``tracks_export_args``). The finished job's ``result`` is the export
        result with ``track_count`` and ``silent``."""
        return self._export_job(self.tracks_export_args(args), t("job.export_tracks"))

    def export_mix(self, args: dict | None = None) -> list[str]:
        """Queue ONE job that exports the mix as one file (see ``mix_export_args``)."""
        return self._export_job(self.mix_export_args(args), t("job.export_mix"))

    def export_folder_hint(self) -> dict:
        """Where an export goes when the caller names no folder: the folder the
        last export of this project used (``remembered``), else ``<project> exports``
        beside the project, which is made only when an export runs. The desktop
        folder chooser starts here."""
        with self.lock:
            saved = self.history.meta_json("export", {}).get("folder")
        if saved:
            return {"folder": str(saved), "remembered": True}
        default = self.package.path.parent / f"{self.package.path.stem} exports"
        return {"folder": str(default), "remembered": False}

    def last_export_settings(self, kind: str) -> dict | None:
        """Return the project's remembered settings for an export kind."""
        return export_module.last_settings(self, kind)

    def loudness_curve(self) -> dict:
        """Short-term loudness per track and for the mix, with the mix's
        integrated LUFS and true peak (WP49, ``loudness_curve``). Measuring
        takes seconds on a long programme, so it works on a snapshot and the
        lock is not held; cached by content, so an edit costs only what it
        changed."""
        with self.lock:
            state = self.history.state
        return loudness_curve_module.project_curves(
            state, self.store, getattr(self.store, "cache_root", None))

    def music_report(self, *, format: str = "rows",
                     title: str | None = None) -> tuple[Any, ...] | str | list[dict]:
        """Royalty music report (WP25): every audible music use in this edit.

        ``format``:
        - ``"rows"`` (default): tuple of :class:`ReportRow` dataclasses.
        - ``"json"``: list of row dicts.
        - ``"csv"``: semicolon-separated UTF-8 string with BOM.
        - ``"html"``: printable HTML document string.
        """
        if format not in ("rows", "json", "csv", "html"):
            raise music_report_module.MusicReportError("error.music_report.bad_format",
                                                       format=format)
        # The state is immutable, so a snapshot is enough: the speech analysis
        # behind the report can take seconds, and must not block edits.
        with self.lock:
            state = self.history.state
        rows = music_report_module.build_report(state, self.store)
        if format == "rows":
            return rows
        if format == "json":
            return [asdict(r) for r in rows]
        if format == "csv":
            return music_report_module.render_csv(rows)
        return music_report_module.render_html(rows, title=title)

    def subtitles(self, format: str) -> str:
        """Export timeline transcript as subtitles text (SRT or WebVTT).

        ``format``:
        - ``"srt"``: SubRip subtitle format (.srt).
        - ``"vtt"``: WebVTT subtitle format (.vtt).
        """
        if format not in ("srt", "vtt"):
            raise SubtitlesError("error.subtitles.bad_format", format=format)
        with self.lock:
            state = self.history.state
            words_by_media = self.transcripts()
        words = transcript.timeline_words(state, words_by_media)
        cue_list = subtitles.cues(words, rate=state.rate)
        if format == "srt":
            return subtitles.to_srt(cue_list)
        return subtitles.to_vtt(cue_list)

    def transcript_text(self, format: str) -> str:
        """The timeline transcript as readable text: ``"txt"`` or ``"md"``.

        The snapshot is taken under the lock; the text is built outside it.
        """
        if format not in ("txt", "md"):
            raise TranscriptTextError("error.transcript_text.bad_format", format=format)
        with self.lock:
            state = self.history.state
            words_by_media = self.transcripts()
        words = transcript.timeline_words(state, words_by_media)
        paras = transcript_text.paragraphs(words, rate=state.rate)
        if format == "txt":
            return transcript_text.to_text(paras)
        return transcript_text.to_markdown(paras)

    def narration_script(self) -> list[dict]:
        """The narration placeholders in timeline order, each with its text,
        start (``m:ss``), estimated length and the 20 words of the episode
        before and after it (``narration.script``). The snapshot is taken under
        the lock; the context is built outside it."""
        with self.lock:
            state = self.history.state
            words_by_media = self.transcripts()
        words = transcript.timeline_words(state, words_by_media)
        return narration.script(state, words)

    def narration_script_text(self, format: str) -> str:
        """The narration script as ``"txt"`` or ``"md"``, for the narrator."""
        if format not in ("txt", "md"):
            raise NarrationScriptError("error.narration_script.bad_format",
                                       format=format)
        items = self.narration_script()
        if format == "txt":
            return narration_script.to_text(items)
        return narration_script.to_markdown(items)

    def cut_preview(self, selected: list[dict]) -> dict[str, Any]:
        """Preview crosstalk that cutting ``selected`` words would remove (WP18).

        ``selected`` is a list of word refs (``track``, ``clip``, ``index``).
        Returns ``{"span": [start, end], "other_words": [...],
        "audio": {track_id: [[start, end], ...]}}``.
        """
        with self.lock:
            state = self.history.state
            transcripts = self.transcripts()
        res = collateral.cut_collateral(state, transcripts, selected)
        return {
            "span": list(res.span),
            "other_words": list(res.other_words),
            "audio": {t: [list(r) for r in ranges] for t, ranges in res.audio.items()},
        }

    def source_map(self, media_sha256: str) -> dict[str, Any]:
        """Source map for a recording (where it is used on the timeline).

        Returns ``{"clips": [...], "used": [...], "cut": [...],
        "unused": [...], "parts": {clip_id: [n, of]}}``.
        """
        with self.lock:
            state = self.history.state
        if not any(m.sha256 == media_sha256 for m in state.media):
            raise ops.EditError("error.edit.no_media", media_id=media_sha256)
        clips = source_map.recording_clips(state, media_sha256)
        used, cut, unused = source_map.coverage(state, media_sha256)
        parts = source_map.part_numbers(state, media_sha256)
        return {
            "clips": [list(c) for c in clips],
            "used": [list(r) for r in used],
            "cut": [list(r) for r in cut],
            "unused": [list(r) for r in unused],
            "parts": {clip_id: list(pair) for clip_id, pair in parts.items()},
        }

    # -- cut candidates (WP18) -----------------------------------------------
    #
    # Candidates live in the material root (``candidates``: id -> record), so
    # every edit sees them and each change is one undoable material step.
    # Detection takes its snapshot under the lock, works outside it (it can
    # take seconds on a long session, and the level analysis reads audio),
    # and commits under the lock again, merged with what is stored *then*:
    # a decision made meanwhile is never overwritten.

    def _candidates_store(self) -> tuple[dict, dict]:
        root = self.history.material
        return root, dict(root.get("candidates", {}))

    def candidates(self, state: str | None = None) -> dict:
        """Every candidate as ``candidates.view`` shows it, by timeline start
        (those no longer on the timeline last), and the counts per state."""
        with self.lock:
            project = self.history.state
            _, stored = self._candidates_store()
        index = candidates.ClipIndex(project)
        rows = [candidates.view(project, candidates.Candidate.from_record(i, r), index)
                for i, r in stored.items() if state is None or r.get("state") == state]
        rows.sort(key=lambda r: (r["start"] is None, r["start"] or 0, r["id"]))
        return {"candidates": rows, "summary": candidates.summary(stored)}

    def candidates_detect(self, *, levels: bool = False,
                          lang: str | None = None) -> dict:
        """Find candidates in the transcripts (and, with ``levels``, in the
        speech levels) and store them as one material step; nothing is
        committed when nothing changed. Returns ``{"added", "dropped"}`` and
        the counts per state."""
        with self.lock:
            project = self.history.state
            words = self.transcripts()
        silences = self._level_silences(project) if levels else None
        found = candidates.detect(project, words, silences=silences, lang=lang)
        with self.lock:
            root, stored = self._candidates_store()
            new, changes = candidates.merge(stored, found, self.history.state)
            if new != stored:
                root["candidates"] = new
                self._material_step(t("history.candidates_detected", **changes), root,
                                    "candidates_detect",
                                    {"levels": bool(levels), "lang": lang})
            return {**changes, **candidates.summary(new)}

    def _level_silences(self, project: Project) -> dict[str, list] | None:
        """Media id -> quiet ranges (flicks from its start) from the speech
        levels: where its mic is closed, plus whatever of the file no clip
        plays (nothing of it is heard there). Reads audio, so never under the
        lock. A failure costs the level data, never the detection."""
        try:
            closed = analysis.raw_silence_ranges(project, self.store)
        except (KuulasError, OSError, ValueError) as e:
            log.warning(t("log.candidates.levels_failed", error=str(e)))
            return None
        out: dict[str, list] = {}
        played: dict[str, list] = {}
        rate = project.rate
        for track in project.tracks:
            for clip in track.clips:
                played.setdefault(clip.media, []).append(
                    (clip.offset, clip.offset + clip.length))
                if track.id not in closed:
                    continue
                quiet = out.setdefault(clip.media, [])
                for a, b in closed[track.id]:
                    lo, hi = max(a, clip.start), min(b, clip.end)
                    if lo < hi:
                        quiet.append(
                            (frames_to_flicks(clip.offset + lo - clip.start, rate),
                             frames_to_flicks(clip.offset + hi - clip.start, rate)))
        for media_id, quiet in out.items():
            at = 0
            for a, b in sorted(played.get(media_id, ())):
                if a > at:
                    quiet.append((frames_to_flicks(at, rate), frames_to_flicks(a, rate)))
                at = max(at, b)
            end = project.media_item(media_id).frames
            if at < end:
                quiet.append((frames_to_flicks(at, rate), frames_to_flicks(end, rate)))
        return out

    def candidate_set_state(self, cid: str, state: str) -> None:
        """Open, cut or kept (K rejects: kept, and never proposed again). One
        undo step; setting the state it already has commits nothing."""
        with self.lock:
            root, stored = self._candidates_store()
            new = candidates.set_state(stored, cid, state)
            if new == stored:
                return
            root["candidates"] = new
            c = candidates.get(new, cid)
            self._material_step(
                t("history.candidate_state", state=_state_word(state),
                  reason=candidates.reason_text(c)),
                root, "candidate_set_state", {"id": cid, "state": state})

    def candidate_apply(self, cid: str, mode: str = "soft",
                        tracks: list[str] | None = None) -> dict:
        """Accept a candidate: the soft cut (mute in place, gap kept) or, with
        ``mode="ripple"``, the cut that closes the gap, and its state ``cut``,
        as one undo step. Returns the spans cut and the tracks touched."""
        with self.lock:
            project = self.history.state
            root, stored = self._candidates_store()
            c = candidates.get(stored, cid)
            if c.state == "cut":
                raise candidates.CandidateError("error.candidates.already_cut", id=cid)
            plan = candidates.apply_plan(project, c, tracks, mode)
            root["candidates"] = candidates.set_state(stored, cid, "cut")
            reason = candidates.reason_text(c)
            label = (t("history.candidate_deleted", reason=reason) if mode == "soft"
                     else t("history.candidate_cut", reason=reason))
            self._commit(label, plan.project, "candidate_apply",
                         {"id": cid, "mode": mode, "tracks": tracks}, material=root)
        return {"mode": plan.mode, "spans": [list(x) for x in plan.spans],
                "tracks": list(plan.tracks)}

    def candidate_preview(self, cid: str, mode: str = "soft",
                          tracks: list[str] | None = None) -> dict:
        """"Play as if cut": where to start and stop, and the frames to skip.
        Nothing is committed."""
        with self.lock:
            project = self.history.state
            _, stored = self._candidates_store()
        plan = candidates.apply_plan(project, candidates.get(stored, cid), tracks, mode)
        return {**plan.preview, "tracks": list(plan.tracks)}

    def candidate_mark(self, start: int, end: int, track_id: str | None = None) -> str:
        """A user's candidate (D) over timeline ``[start, end)`` on ``track_id``;
        one undo step. Returns its id (the same range marked twice is one)."""
        with self.lock:
            project = self.history.state
            if track_id is not None:
                ops._find_track(project, track_id)  # an unknown track is an EditError
            c = candidates.mark(project, int(start), int(end), track_id)
            root, stored = self._candidates_store()
            new = candidates.add(stored, c)
            if new != stored:
                root["candidates"] = new
                self._material_step(t("history.candidate_marked"), root,
                                    "candidate_mark", {"start": int(start),
                                                       "end": int(end),
                                                       "track_id": track_id})
            return c.id

    # -- import ------------------------------------------------------------

    def import_media(self, paths: list[str], copy: bool = False,
                     track_per_file: bool = True, interview: bool | None = None,
                     interview_title: str | None = None, *,
                     mode: str | None = None, order: str = "given",
                     track_naming: str = "file", start_frame: int = 0) -> Project:
        """``import_media_report`` without the report (it stays in
        ``last_import_report``). Raises if not one file could be imported."""
        return self.import_media_report(paths, copy=copy, track_per_file=track_per_file,
                                        interview=interview,
                                        interview_title=interview_title,
                                        mode=mode, order=order,
                                        track_naming=track_naming,
                                        start_frame=start_frame)[0]

    def import_media_report(self, paths: list[str], copy: bool = False,
                            track_per_file: bool = True, interview: bool | None = None,
                            interview_title: str | None = None, *,
                            mode: str | None = None, order: str = "given",
                            track_naming: str = "file", start_frame: int = 0,
                            ) -> tuple[Project, list[ImportResult]]:
        """Bring files in and put them on the timeline, as ONE undo step.

        Fail soft (WP34): a file that cannot be imported is left out and
        named in the report with the reason; the others still come in. Only
        when none can does this raise (that file's own error if it was the
        only one), and then nothing changes.

        Placement options (WP34 pure plan):
        - ``mode``: ``"side_by_side"`` (one track per file) or ``"sequential"``
          (one track for all). ``None`` keeps ``track_per_file`` as the switch.
        - ``order``: ``"given"``, ``"name"`` (case-insensitive natural sort) or
          ``"time"``. When placing with ``order="name"`` or ``"time"``, the first
          clip in the sync group is the first placed one.
        - ``track_naming``: ``"file"`` (name without extension) or ``"person"``.
        - ``start_frame``: timeline frame where placement begins (default 0).

        Files imported side-by-side were recorded together, so they are one
        sync group, placed by their recorders' clocks (BWF time reference,
        relative to the earliest; a file without one starts at ``start_frame``).
        A file that does not belong (a Zoom or phone recording) is aligned
        by hand and marked in sync later. ``sequential`` puts the files one after
        another on a single track; that is not the same moment, so no group.

        **One interview (WP41).** Files imported together are offered as one
        interview: ``interview=None`` (the default) makes it exactly when they
        became a sync group; ``True``/``False`` decide. It is part of the same
        undo step, named ``interview_title`` or after the first file. Files
        that already belong to an interview are not put in a second one.
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
            root = self.history.material

            if mode is not None:
                effective_mode = mode
            else:
                effective_mode = "side_by_side" if track_per_file else "sequential"

            people = root.get("people", {})
            media_person_map = root.get("media_person", {})

            def _person_name(m) -> str | None:
                pid = media_person_map.get(m.id) or m.person
                if pid and pid in people:
                    return people[pid].get("name", pid)
                return pid or None

            items = [
                import_plan.ImportItem(
                    name=m.name,
                    frames=m.frames,
                    channels=m.channels,
                    time_ref_flicks=m.time_ref_flicks,
                    person=_person_name(m),
                )
                for m in media
            ]

            placements = import_plan.plan_import(
                items,
                p.rate,
                mode=effective_mode,
                start_frame=start_frame,
                order=order,
                track_naming=track_naming,
            )

            media_pool: dict[import_plan.ImportItem, list] = {}
            for item, m in zip(items, media, strict=True):
                media_pool.setdefault(item, []).append(m)

            track_ids_by_key: dict[str, str] = {}
            clip_ids: list[str] = []
            for pl in placements:
                m = media_pool[pl.item].pop(0)
                if pl.new_track:
                    track_id = ops.new_id("t")
                    track_ids_by_key[pl.track_key] = track_id
                    p = ops.add_track(p, track_id, pl.track_name, pl.kind)
                    if pl.mono:
                        p = ops.set_track(p, track_id, mono=True)
                else:
                    track_id = track_ids_by_key[pl.track_key]
                clip_id = ops.new_id("c")
                p = ops.add_clip(p, track_id, m.id, start=pl.start_frame, clip_id=clip_id)
                clip_ids.append(clip_id)

            refs = [m.time_ref_flicks for m in media]
            if effective_mode == "side_by_side" and len({m.id for m in media}) > 1:
                # Exact clocks when every file has one (or none does); mixed,
                # the files that have none were placed at 0, so the placement
                # on the timeline is what the group has to say.
                basis = "files" if len({r is None for r in refs}) == 1 else "timeline"
                p = ops.mark_in_sync(p, clip_ids, main=clip_ids[0], basis=basis)
            self.last_import_stereo = [
                {"id": track_ids_by_key[pl.track_key], "name": pl.track_name}
                for pl in import_plan.stereo_speech(placements)]
            label = t("history.import", count=len(media))
            distinct_media = len({m.id for m in media}) > 1
            made_group = (
                bool(p.sync_groups)
                and (effective_mode == "side_by_side")
                and distinct_media
            )
            root = self._with_import_interview(
                p, media, interview, interview_title, made_group)
            # Only what came in is recorded: replaying the step must not
            # depend on files that failed.
            return (self._commit(label, p, "import_media",
                                 {"paths": [x for x, _ in ok], "copy": copy,
                                  "track_per_file": track_per_file,
                                  "mode": mode,
                                  "order": order,
                                  "track_naming": track_naming,
                                  "start_frame": start_frame,
                                  "interview": self.last_import_interview},
                                 material=root), report)

    def rebuild_media(self, media_id: str, path: str | Path | None = None) -> str:
        """Re-encode a damaged working file from its original file."""
        # The re-encode of a long file takes a while and the store has its own
        # locks, so only the quick metadata lookup is done under the session
        # lock (ground rule 14).
        target = self.store.rebuild(media_id, path)
        with self.lock:
            name = self.store.meta(media_id)["name"]
        return t("media.rebuilt", name=name, path=str(target))

    def import_nhsx(self, path: str | Path) -> Project:
        """Import a Hindenburg session with regions and words on source clocks."""
        source = Path(path)
        try:
            nhsx_session = read_nhsx(source)
            pipeline_tracks = nhsx_tracks(nhsx_session, with_probe=False)
            mix_clips = nhsx_mix_plan(nhsx_session).clips
            source_xml = _element_xml(nhsx_session.tree.getroot())
        except (NhsxError, OSError, ValueError):
            raise NhsxImportError("error.import.nhsx_failed", path=str(source)) from None

        available = {str(Path(track.path).resolve()) for track in pipeline_tracks}
        paths = {}
        missing = []
        for file_info in nhsx_session.files:
            found = nhsx_locate(nhsx_session, file_info)
            if found and str(Path(found).resolve()) in available:
                paths[file_info.id] = str(Path(found).resolve())
            else:
                missing.append(ImportResult(
                    Path(file_info.path or file_info.name),
                    error=MediaError("error.import.nhsx_missing_media",
                                     name=file_info.name)))

        resolved_paths = list(dict.fromkeys(paths.values()))
        imported = (self.store.import_batch(resolved_paths, copy=False)
                    if resolved_paths else [])
        self.last_import_report = [*missing, *imported]
        media_by_path = {str(Path(result.path).resolve()): result.media
                         for result in imported if result.ok and result.media is not None}
        media_by_file = {file_id: media_by_path[file_path]
                         for file_id, file_path in paths.items()
                         if file_path in media_by_path}

        p = self.history.state
        for file_info in nhsx_session.files:
            media = media_by_file.get(file_info.id)
            if media is None:
                continue
            enriched = replace(media, extra={**media.extra, "nhsx": {
                "source_xml": _element_xml(file_info.elem)}})
            stored_extra = json.loads(self.store.meta(media.id)["extra"] or "{}")
            stored_extra["nhsx"] = enriched.extra["nhsx"]
            self.store.set_extra(media.id, stored_extra)
            media_by_file[file_info.id] = enriched
            media_by_path[paths[file_info.id]] = enriched

        for media in media_by_path.values():
            if not any(item.id == media.id for item in p.media):
                p = ops.add_media(p, media)

        mix_by_region = {}
        for clip in mix_clips:
            key = (clip.speaker, str(Path(clip.path).resolve()), clip.start,
                   clip.length, clip.file_offset)
            mix_by_region.setdefault(key, []).append(clip)

        for source_track in nhsx_session.tracks:
            track_id = None
            track_elem = source_track.elem
            track_gain = (_db_value(track_elem.get("Gain"))
                          + _db_value(track_elem.get("Volume")))
            track_pan = max(-1.0, min(1.0, _db_value(track_elem.get("Pan"))))
            track_muted = _truth(track_elem.get("Muted"))
            for region in source_track.regions:
                file_path = paths.get(region.ref)
                media = media_by_file.get(region.ref)
                if file_path is None or media is None:
                    continue
                start = round(region.start * self.history.rate)
                offset = round(region.offset * self.history.rate)
                length = round(region.length * self.history.rate)
                if offset < 0 or offset >= media.frames or length <= 0:
                    continue
                length = min(length, media.frames - offset)
                if length <= 0:
                    continue
                if track_id is None:
                    track_id = ops.new_id("t")
                    kind = import_plan.guess_kind(source_track.name or "")
                    p = ops.add_track(p, track_id, source_track.name or "Track", kind)
                    p = ops.set_track(p, track_id, gain_db=track_gain, pan=track_pan,
                                      mute=track_muted)
                    p = ops.set_track_extra(p, track_id, "nhsx", {
                        "source_xml": _element_xml(track_elem)})
                clip_id = ops.new_id("c")
                p = ops.add_clip(p, track_id, media.id, start=start, offset=offset,
                                 length=length, clip_id=clip_id)
                elem = region.elem
                levels = _region_levels(elem, self.history.rate)
                p = ops.set_clip(p, clip_id, gain_db=levels["gain_db"],
                                 pan=levels["pan"], fade_in=levels["fade_in"],
                                 fade_out=levels["fade_out"], muted=levels["muted"])
                p = ops.set_clip_extra(p, clip_id, "nhsx", {
                    "source_xml": _element_xml(elem)})
                key = (source_track.name, file_path, region.start, region.length,
                       region.offset)
                ramps = mix_by_region.get(key, [])
                if ramps:
                    ramp = ramps.pop(0)
                    points = _ramp_points(ramp.ramps, region.offset, self.history.rate)
                    if points:
                        p = ops.set_clip_envelope(p, clip_id, points)

        root = self.history.material
        with dbm.tx(self.history.db):
            for file_id, media in media_by_file.items():
                if media.id in root["transcripts"]:
                    continue
                file_info = nhsx_session.file_by_id(file_id)
                words = _nhsx_words(file_info)
                if not words:
                    continue
                digest = dbm.put_blob(self.history.db, "words", words)
                cur = self.history.db.execute(
                    "insert into transcript_revs(media, parent, words, engine, "
                    "created_utc)"
                    " values (?,?,?,?,?)",
                    (media.id, None, digest, '{"tool":"nhsx"}', dbm.utc_now()))
                root["transcripts"][media.id] = int(cur.lastrowid)

        self.last_import_clipboard = self._import_nhsx_clipboard(
            nhsx_session, media_by_file)
        if p == self.history.state and root == self.history.material:
            return p
        p = replace(p, extra={**p.extra, "nhsx": {"source_xml": source_xml}})
        self.last_import_interview = None
        self.last_import_stereo = []
        return self._commit(t("history.nhsx_import", name=source.name), p,
                            "import_nhsx", {"path": str(source)}, material=root)

    def _import_nhsx_clipboard(self, nhsx_session, media_by_file: dict) -> int:
        """Turn the session's non-empty clipboard clips into pinned entries of
        the user's clipboard history; return how many came in. A clip that
        cannot become an entry is skipped with a log line, never an error."""
        entries = []
        for number, clip in _nhsx_clipboard_clips(nhsx_session.tree.getroot()):
            name = t("clipboard.nhsx_entry", number=number, name=clip.get("Name", ""))
            try:
                entries.append(self._nhsx_clipboard_entry(
                    clip, name, media_by_file, nhsx_session))
            except ValueError as e:
                reason = str(e)
                if reason.startswith("log.import."):
                    reason = t(reason)
                log.warning(t("log.import.nhsx_clipboard_skipped", name=name,
                              error=reason))
        if not entries:
            return 0
        try:
            # The first group ends up on top of the history.
            for entry in reversed(entries):
                self.clipboard.update(lambda h, e=entry: h.add(e))
        except OSError as e:
            log.warning(t("log.clipboard.copy_failed", error=str(e)))
            return 0
        return len(entries)

    def _nhsx_clipboard_entry(self, clip, name: str, media_by_file: dict,
                              nhsx_session) -> Entry:
        rate = self.history.rate
        tracks = sorted({r.get("Track", "0") for r in nhsx_children(clip, "Region")})
        refs = []
        for region in nhsx_children(clip, "Region"):
            media = media_by_file.get(region.get("Ref", ""))
            if media is None:
                raise ValueError("log.import.nhsx_clipboard_unknown_ref")
            offset = round(nhsx_time_to_seconds(region.get("Offset", "0")) * rate)
            length = round(nhsx_time_to_seconds(region.get("Length")) * rate)
            if offset < 0 or offset >= media.frames or length <= 0:
                raise ValueError("log.import.nhsx_clipboard_bad_region")
            levels = _region_levels(region, rate)
            refs.append(ClipRef(
                media.sha256, offset, min(length, media.frames - offset),
                rel_start=round(nhsx_time_to_seconds(region.get("Start", "0")) * rate),
                track_slot=tracks.index(region.get("Track", "0")), **levels))
        if not refs:
            raise ValueError("log.import.nhsx_clipboard_bad_region")
        end = max(ref.rel_start + ref.length for ref in refs)
        end = max(end, round(_time_value(clip.get("Length")) * rate))
        names = []
        for index in tracks:
            try:
                names.append(nhsx_session.tracks[int(index)].name)
            except (ValueError, IndexError):
                names.append("")
        return entry_from_refs(refs, name=name, span=(0, end), pinned=True,
                               source_project=str(self.package.path),
                               extra={"tracks": names})

    def _with_import_interview(self, p: Project, media: list, want: bool | None,
                               title: str | None, made_group: bool) -> dict | None:
        """The material root with the import's interview in it, or None."""
        self.last_import_interview = None
        if not (made_group if want is None else want) or not media:
            return None
        root = self.history.material
        taken = {sha for d in root["interviews"].values() for sha in d.get("media", ())}
        shas = [m.sha256 for m in {m.id: m for m in media}.values()
                if m.sha256 not in taken]
        if not shas:
            return None
        group = p.sync_group(media[0].id)
        iid = dbm.uuid7()
        root["interviews"][iid] = Interview(
            iid, title or Path(media[0].name).stem, media=tuple(shas),
            sync_group=group.id if made_group and group else "").to_dict()
        self.last_import_interview = iid
        return root

    # -- people, interviews, who speaks (WP41) ------------------------------

    def people(self) -> list[Person]:
        with self.lock:
            return list(self.history.people())

    def person(self, person_id: str) -> Person:
        with self.lock:
            return Person.from_dict({**self._known_person(person_id), "id": person_id})

    def interviews(self) -> list[Interview]:
        with self.lock:
            return list(self.history.interviews())

    def interview(self, interview_id: str) -> Interview:
        with self.lock:
            try:
                d = self.history.material["interviews"][interview_id]
            except KeyError:
                raise ops.EditError("error.people.no_interview",
                                    interview_id=interview_id) from None
            return Interview.from_dict({**d, "id": interview_id})

    def interview_of(self, media_id: str) -> Interview | None:
        """The interview a file belongs to, if any."""
        with self.lock:
            sha = self._sha(media_id)
            return next((i for i in self.history.interviews() if sha in i.media), None)

    def speaker_map(self, media_id: str) -> dict[str, str]:
        with self.lock:
            return self.history.speaker_map(media_id)

    def passages(self, person_id: str) -> list[Passage]:
        """Every passage by a person in this project (``History.passages``).

        TODO(WP37/WP38): across a series, read each project's usage file for
        the usage marks; until those exist ``series.passages_in_projects``
        gives the passages of several projects without marks.
        """
        with self.lock:
            return self.history.passages(person_id)

    def _known_person(self, person_id: str) -> dict:
        try:
            return self.history.material["people"][person_id]
        except KeyError:
            raise ops.EditError("error.people.no_person", person_id=person_id) from None

    def _sha(self, media_id: str) -> str:
        try:
            return self.history.state.media_item(media_id).sha256
        except KeyError:
            raise ops.EditError("error.edit.no_media", media_id=media_id) from None

    def _check_people(self, ids) -> None:
        for person_id in ids:
            if person_id:
                self._known_person(person_id)

    def create_person(self, name: str, role: str = "", aliases=(), notes: str = "",
                      ) -> str:
        """A new person; returns their id. One undo step."""
        with self.lock:
            name = name.strip()
            if not name:
                raise ops.EditError("error.people.empty_name")
            pid = dbm.uuid7()
            root = self.history.material
            root["people"][pid] = Person(pid, name, tuple(aliases), role, notes).to_dict()
            self._material_step(t("history.person_created", name=name), root,
                                "create_person", {"id": pid, "name": name, "role": role,
                                                  "aliases": list(aliases),
                                                  "notes": notes})
            return pid

    def edit_person(self, person_id: str, **fields) -> None:
        """Change a person's ``name``, ``role``, ``aliases`` or ``notes``."""
        with self.lock:
            old = self._known_person(person_id)
            self._check_fields(fields, ("name", "role", "aliases", "notes"))
            new = Person.from_dict({**old, **fields, "id": person_id})
            if not new.name.strip():
                raise ops.EditError("error.people.empty_name")
            root = self.history.material
            root["people"][person_id] = new.to_dict()
            self._material_step(t("history.person_edited", name=new.name), root,
                                "edit_person", {"id": person_id, **fields})

    def delete_person(self, person_id: str) -> None:
        """Remove a person. One undo step."""
        with self.lock:
            old = self._known_person(person_id)
            root = self.history.material
            del root["people"][person_id]
            for mid, pid in list(root.get("media_person", {}).items()):
                if pid == person_id:
                    del root["media_person"][mid]
            for iid, data in list(root.get("interviews", {}).items()):
                parts = [p for p in data.get("participants", ())
                         if p.get("person") != person_id]
                if len(parts) != len(data.get("participants", ())):
                    root["interviews"][iid]["participants"] = parts
            for mid, spk_map in list(root.get("speakers", {}).items()):
                cleaned = {lbl: pid for lbl, pid in spk_map.items() if pid != person_id}
                if len(cleaned) != len(spk_map):
                    root["speakers"][mid] = cleaned
            self._material_step(t("history.person_deleted", name=old["name"]), root,
                                "delete_person", {"id": person_id})

    @staticmethod
    def _check_fields(fields: dict, allowed: tuple[str, ...]) -> None:
        for name in fields:
            if name not in allowed:
                raise ops.EditError("error.people.bad_field", field=name)

    def create_interview(self, title: str, date: str = "", place: str = "",
                         participants=(), media=(), sync_group: str = "",
                         notes: str = "", tags=()) -> str:
        """A new interview of the given media (ids); returns its id. When no
        ``sync_group`` is given and the files share one, that is used."""
        with self.lock:
            shas = [self._sha(m) for m in media]
            self._check_people(p.get("person") for p in participants)
            if not sync_group:
                groups = {g.id if (g := self.history.state.sync_group(m)) else ""
                          for m in media}
                sync_group = groups.pop() if len(groups) == 1 else ""
            iid = dbm.uuid7()
            root = self.history.material
            root["interviews"][iid] = Interview(
                iid, title, date, place, tuple(dict(p) for p in participants),
                tuple(dict.fromkeys(shas)), sync_group, notes, tuple(tags)).to_dict()
            self._material_step(t("history.interview_created", title=title), root,
                                "create_interview", {"id": iid, "title": title,
                                                     "media": list(media)})
            return iid

    def edit_interview(self, interview_id: str, **fields) -> None:
        """Change an interview's ``title``, ``date``, ``place``, ``participants``,
        ``media`` (media ids), ``sync_group``, ``notes`` or ``tags``."""
        with self.lock:
            old = self.interview(interview_id).to_dict()
            self._check_fields(fields, ("title", "date", "place", "participants",
                                        "media", "sync_group", "notes", "tags"))
            changes = dict(fields)
            if "media" in changes:
                changes["media"] = list(dict.fromkeys(
                    self._sha(m) for m in changes["media"]))
            if "participants" in changes:
                self._check_people(p.get("person") for p in changes["participants"])
            new = Interview.from_dict({**old, **changes})
            root = self.history.material
            root["interviews"][interview_id] = new.to_dict()
            self._material_step(t("history.interview_edited", title=new.title), root,
                                "edit_interview", {"id": interview_id, **fields})

    def delete_interview(self, interview_id: str) -> None:
        """Remove an interview. One undo step."""
        with self.lock:
            old = self.interview(interview_id)
            root = self.history.material
            del root["interviews"][interview_id]
            self._material_step(t("history.interview_deleted", title=old.title), root,
                                "delete_interview", {"id": interview_id})

    def set_media_person(self, media_id: str, person_id: str | None) -> None:
        """Say whose voice a single-person mic file holds (None clears it)."""
        with self.lock:
            self._sha(media_id)
            self._check_people([person_id])
            root = self.history.material
            if person_id:
                root["media_person"][media_id] = person_id
            else:
                root["media_person"].pop(media_id, None)
            name = self._known_person(person_id)["name"] if person_id else "-"
            self._material_step(t("history.media_person", media_id=media_id, name=name),
                                root, "set_media_person",
                                {"media": media_id, "person": person_id})

    def set_music_info(self, media_id: str, fields: dict) -> None:
        """Edit music tags (title, artist, composer, publisher, isrc) in material root.

        An empty string blanks a tag; ``None`` removes the edit, so the
        imported tag returns."""
        with self.lock:
            self._sha(media_id)
            allowed = {"title", "artist", "composer", "publisher", "isrc"}
            for k in fields:
                if k not in allowed:
                    raise ops.EditError("error.edit.bad_music_key", key=k)
            root = self.history.material
            if "music_info" not in root:
                root["music_info"] = {}
            current_edits = dict(root["music_info"].get(media_id, {}))
            # "" blanks a field even when the import found a value; None drops
            # the edit, so the imported value shows again.
            for k, v in fields.items():
                if v is None:
                    current_edits.pop(k, None)
                else:
                    current_edits[k] = str(v)
            if current_edits:
                root["music_info"][media_id] = current_edits
            else:
                root["music_info"].pop(media_id, None)
            self._material_step(t("history.set_music_info", media_id=media_id),
                                root, "set_music_info",
                                {"media": media_id, "fields": dict(fields)})

    def map_speakers(self, media_id: str, mapping: dict[str, str | None]) -> None:
        """Map the speaker labels of the transcript ``media_id`` uses to people
        (the whole map: labels left out are nobody). The words are not
        touched; a re-transcription starts with an empty map."""
        with self.lock:
            rev = self.history.transcript_rev(media_id)
            if rev is None:
                raise ops.EditError("error.people.no_transcript", media_id=media_id)
            self._check_people(mapping.values())
            root = self.history.material
            root["speakers"][str(rev)] = {k: v or "" for k, v in mapping.items()}
            self._material_step(t("history.speakers_mapped", media_id=media_id), root,
                                "map_speakers", {"media": media_id, "map": dict(mapping)})

    # -- transcripts -------------------------------------------------------

    def transcripts(self) -> dict[str, list[dict]]:
        """Media id -> its words (flicks from the media's start), as the
        material says they are now, with ``person`` where it is known (it is
        resolved here, never stored). A revision is read once and kept."""
        with self.lock:
            root = self.history.material
            out = {}
            for media_id, stored in root["transcripts"].items():
                rev = int(stored)
                owner = root["media_person"].get(media_id, "")
                labels = root["speakers"].get(str(rev), {})
                # A revision never changes once stored, so it is kept (in the
                # memory budget) for as long as there is room for it; with
                # the people it resolves to, it is a different value.
                out[media_id] = self._memo(
                    "words", self._view_key(rev, owner, sorted(labels.items())),
                    lambda rev=rev, media_id=media_id, root=root:
                        self.history.resolved_words(media_id, rev, root), 150)
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

    def transcribe(self, media_ids: list[str], model: str = "small",
                   language: str | None = None) -> list[str]:
        """Queue one local transcript job for every selected media item."""
        ids = list(dict.fromkeys(media_ids))
        job_ids = []
        cpu_threads = max(1, (os.cpu_count() or 2) // self.jobs.max_workers)
        for media_id in ids:
            with self.lock:
                try:
                    item = self.history.state.media_item(media_id)
                except KeyError:
                    raise ops.EditError(
                        "error.edit.no_media", media_id=media_id) from None
                source = self.store.transcription_path(media_id)
                previous = self.history.material["transcripts"].get(media_id)
                title = t("job.transcribe", name=item.name)

            def run(progress, source=source):
                return transcribe.local(source, model=model, language=language,
                                        progress=progress, cpu_threads=cpu_threads)

            def commit(words, media_id=media_id, previous=previous):
                with self.lock:
                    current = self.history.material["transcripts"].get(media_id)
                    if current != previous:
                        raise KuulasError("error.transcribe.changed")
                    self.set_transcript(media_id, words,
                                        t("history.transcript", media_id=media_id))

            job_ids.append(self.jobs.submit("transcribe", title, run, commit))
        return job_ids

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
            # The material head stands for who speaks (WP41): equal head,
            # equal people, maps and revisions.
            key = self._view_key(self.history.edit_hash, self.history.rate, revs,
                                 self.history.material_head)

            def compute() -> list[dict]:
                return transcript.timeline_words(self.history.state, self.transcripts())

            return list(self._memo("timeline_words", key, compute, 300))

    def edit_points(self, mode: str, track_id: str | None = None) -> list[int]:
        """The Tab stops of ``mode`` (WP19i), memoized on the edit state, so
        the same head asked twice costs nothing. Onset detection reads media
        (cached per file by content), so it runs on a snapshot with the lock
        released; edit points of an old head are never served for a new one."""
        if mode not in edit_points.MODES:
            raise edit_points.EditPointsError("error.edit_points.unknown_mode", mode=mode)
        with self.lock:
            state = self.history.state
            revs = sorted(self.history.material["transcripts"].items())
            key = self._view_key(self.history.edit_hash, self.history.rate, revs,
                                 self.history.material_head, mode, track_id)
            transcripts = self.transcripts() if mode == "words" else {}

        def compute() -> list[int]:
            found: dict[str, Any] = {}
            if mode == "transients":
                for media in state.media:
                    got = onsets.onsets_for_media(self.store, media.id)
                    if got is not None:
                        found[media.id] = got
            return edit_points.edit_points(state, transcripts, found, mode, track_id)

        return list(self._memo("edit_points", key, compute, 8))

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


def _duck_music(s: Session, args: dict) -> Project:
    new = analysis.duck_music(s.history.state, s.store)
    return s._commit(t("history.duck_music"), new, "duck_music", args)


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


def _create_person(s: Session, args: dict) -> Project:
    s.create_person(args.get("name", ""), args.get("role", ""),
                    args.get("aliases", ()), args.get("notes", ""))
    return s.history.state


def _edit_person(s: Session, args: dict) -> Project:
    s.edit_person(args["id"], **{k: v for k, v in args.items() if k != "id"})
    return s.history.state


def _delete_person(s: Session, args: dict) -> Project:
    s.delete_person(args["id"])
    return s.history.state


def _create_interview(s: Session, args: dict) -> Project:
    s.create_interview(args.get("title", ""),
                       **{k: v for k, v in args.items() if k != "title"})
    return s.history.state


def _edit_interview(s: Session, args: dict) -> Project:
    s.edit_interview(args["id"], **{k: v for k, v in args.items() if k != "id"})
    return s.history.state


def _delete_interview(s: Session, args: dict) -> Project:
    s.delete_interview(args["id"])
    return s.history.state


def _set_media_person(s: Session, args: dict) -> Project:
    s.set_media_person(args["media"], args.get("person"))
    return s.history.state


def _map_speakers(s: Session, args: dict) -> Project:
    s.map_speakers(args["media"], args.get("map", {}))
    return s.history.state


def _import_nhsx(s: Session, args: dict) -> Project:
    return s.import_nhsx(args["path"])


def _rebuild_media(s: Session, args: dict) -> Project:
    media_id = args.get("media") or args.get("id")
    if not media_id:
        raise ops.EditError("error.edit.no_media", media_id="")
    s.rebuild_media(media_id, args.get("path"))
    return s.history.state


def _set_music_info(s: Session, args: dict) -> Project:
    media_id = args.get("media") or args.get("media_id") or args.get("id")
    if not media_id:
        raise ops.EditError("error.edit.no_media", media_id="")
    fields = args.get("fields")
    if fields is None:
        fields = {k: v for k, v in args.items() if k not in ("media", "media_id", "id")}
    s.set_music_info(media_id, fields)
    return s.history.state


def _state_word(state: str) -> str:
    """The state as the history label says it."""
    if state == "cut":
        return t("candidate.state.cut")
    if state == "kept":
        return t("candidate.state.kept")
    return t("candidate.state.open")


def _candidates_detect(s: Session, args: dict) -> Project:
    s.candidates_detect(levels=_truth_arg(args.get("levels")), lang=args.get("lang"))
    return s.state


def _truth_arg(value) -> bool:
    return value is True or (isinstance(value, str) and _truth(value))


def _candidate_id(args: dict) -> str:
    cid = args.get("id")
    if not cid:
        raise candidates.UnknownCandidateError("error.candidates.no_candidate", id="")
    return str(cid)


def _candidate_set_state(s: Session, args: dict) -> Project:
    s.candidate_set_state(_candidate_id(args), str(args.get("state", "")))
    return s.history.state


def _candidate_apply(s: Session, args: dict) -> Project:
    s.candidate_apply(_candidate_id(args), str(args.get("mode", "soft")),
                      args.get("tracks"))
    return s.history.state


def _candidate_mark(s: Session, args: dict) -> Project:
    try:
        start, end = int(args["start"]), int(args["end"])
    except (KeyError, TypeError, ValueError):
        raise ops.EditError("error.edit.bad_arguments", name="candidate_mark",
                            detail="start, end") from None
    s.candidate_mark(start, end, args.get("track_id"))
    return s.history.state


def _match_loudness(s: Session, args: dict) -> Project:
    clip_ids = args.get("clip_ids", [])
    target = args.get("target_lufs")
    target_lufs = None if target is None else float(target)
    return s.match_loudness(clip_ids, target_lufs=target_lufs)


def _placeholder_take(s: Session, args: dict) -> Project:
    """Import ONE file and make it the take of a narration placeholder (WP43),
    as one undo step: the file comes into the project's media, the placeholder
    becomes a clip and the later material moves by the difference in length.
    A file that cannot be imported changes nothing."""
    try:
        placeholder_id, path = args["placeholder_id"], args["path"]
        offset = int(args.get("offset", 0))
    except (KeyError, TypeError, ValueError) as e:
        raise ops.EditError("error.edit.bad_arguments", name="placeholder_take",
                            detail=str(e)) from None
    project = s.history.state
    ops._find_placeholder(project, placeholder_id)  # fail before importing
    result = s.store.import_batch([path], bool(args.get("copy", False)))[0]
    s.last_import_report = [result]
    if not result.ok:
        raise result.error
    new = ops.replace_placeholder(s.history.state, placeholder_id, result.media.id,
                                  offset, bool(args.get("group_editing", True)))
    return s._commit(t("history.placeholder_take"), new, "placeholder_take", args)


def _check_writable(s: Session) -> None:
    if s.read_only:
        holder = s.package.locked_by or {}
        raise ops.EditError("error.history.read_only", host=holder.get("host", "?"))


def _save_backup(s: Session, _args: dict) -> Project:
    """Mod+S: the 10-minute timer's backup, now (same retention). Edits are
    already committed, so this only makes the copy. The online backup reads
    through its own connection, so no session lock: a slow disk must not
    stall playback."""
    _check_writable(s)
    s.last_backup = s.package.backup()
    return s.state


def _save_checkpoint(s: Session, args: dict) -> Project:
    """Shift+Mod+S: name the current step. Changes no edit state."""
    _check_writable(s)
    s.checkpoint(str(args.get("name") or "").strip() or t("history.checkpoint_default"))
    return s.state


#: Name -> function(session, args) -> Project. The session lock is held,
#: except for ``LOCK_FREE_COMMANDS``.
#: ``auto_silence``, ``automix`` and ``cut_words`` commit one step each;
#: ``relink`` and ``consolidate`` change no state and commit nothing. The people
#: commands (WP41) each commit one material-only step.
COMMANDS: dict[str, Callable[[Session, dict], Project]] = {
    "auto_silence": _auto_silence,
    "automix": _automix,
    "duck_music": _duck_music,
    "cut_words": _cut_words,
    "relink": _relink,
    "consolidate": _consolidate,
    "create_person": _create_person,
    "edit_person": _edit_person,
    "delete_person": _delete_person,
    "create_interview": _create_interview,
    "edit_interview": _edit_interview,
    "delete_interview": _delete_interview,
    "set_media_person": _set_media_person,
    "set_music_info": _set_music_info,
    "map_speakers": _map_speakers,
    "import_nhsx": _import_nhsx,
    "rebuild_media": _rebuild_media,
    "candidates_detect": _candidates_detect,
    "candidate_set_state": _candidate_set_state,
    "candidate_apply": _candidate_apply,
    "candidate_mark": _candidate_mark,
    "match_loudness": _match_loudness,
    "placeholder_take": _placeholder_take,
    "save_backup": _save_backup,
    "save_checkpoint": _save_checkpoint,
}

#: Commands that run without the session lock and take it only for their
#: snapshot and their commit: their work is slow and must not stall playback
#: or edits (ground rule 14).
LOCK_FREE_COMMANDS = frozenset({"candidates_detect", "match_loudness", "save_backup"})
