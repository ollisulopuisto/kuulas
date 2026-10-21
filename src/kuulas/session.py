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
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
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
    bgjobs,
    block_level,
    caches,
    candidates,
    clipboard_browse,
    clipboard_level,
    clipboard_link,
    collateral,
    edit_points,
    edit_scope,
    export_names,
    import_plan,
    music_duck,
    music_level,
    narration,
    narration_script,
    offload,
    onsets,
    ops,
    package,
    preview_level,
    priority,
    project_stats,
    render_listen,
    silence_learn,
    silence_options,
    source_map,
    subtitles,
    sync_state,
    transcribable,
    transcript,
    transcript_text,
)
from . import automix as automix_module
from . import chapters as chapters_module
from . import colab_transcribe as colab_module
from . import db as dbm
from . import export as export_module
from . import loudness_curve as loudness_curve_module
from . import markers as markers_module
from . import music_report as music_report_module
from . import send_copy as send_copy_module
from .clipboard import (
    ClipRef,
    Entry,
    adopted_copy,
    entry_from_refs,
    entry_from_view,
    make_entry,
    make_entry_range,
)
from .clipboard_preview import preview_project
from .clipboard_store import ClipboardStore, entry_dict, project_path
from .clipboard_text import entry_text
from .clock import FLICKS, frames_to_flicks
from .history import History, UndoInfo
from .jobs import JobCancelledError, Jobs
from .loudness import gain_to_target, measure_clip, track_target_lufs
from .media import ImportResult, MediaError, MediaStore, file_sha256
from .messages import KuulasError, t
from .model import Project, SyncGroup
from .paste_apply import apply_paste
from .paste_plan import _targets, plan_paste
from .people import Interview, Passage, Person
from .resume import ResumeWriter, now_iso
from .view_memory import ViewMemory

log = logging.getLogger("kuulas.session")


class NhsxImportError(KuulasError, ValueError):
    """A Hindenburg session could not be parsed or mapped safely."""


class NoSuchEntryError(ops.EditError):
    """The clipboard has no entry with that id (the API answers 404)."""


class SubtitlesError(ops.EditError):
    """Unknown subtitle format."""


class SilenceNotMeasuredError(KuulasError):
    """The Auto-Silence live preview has no measure of the project's speech
    audio as it is now: measure first (the API answers 409)."""


class SilenceStaleError(ops.EditError):
    """Accept was asked for a preview of an older audio state (the API
    answers 409): the speech audio changed after the preview was made."""


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
#: A project up to this long is measured for the clipboard preview's reference level
#: while the click waits (a few hundred ms); a longer one is measured in the background.
INLINE_REFERENCE_S = 120.0
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
#: How many printed automixer lines the live log viewer can show.
AUTOMIX_LIVE_LINES = 3000
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


#: Edit ops that act on a rectangle of time by tracks (WP83): with no tracks
#: given they act on all tracks.
RANGE_OPS = frozenset({"cut_range", "clear_range", "mute_range", "ripple_delete"})

#: Edit ops that move clips by id: the members of the clips' explicit groups go
#: along (WP83). Sync partners never do.
GROUPED_OPS = frozenset({"nudge_clips", "move_clips_to_track", "shift_clips"})

#: How many steps back ``sync_cause`` looks for the edit that moved a clip.
CAUSE_STEPS = 300


class Session:
    """``folder`` is the ``Name.kuulas`` package; it is created if it does not
    exist. ``rate`` applies to a new project only: an existing one keeps its own."""

    def __init__(self, folder: str | Path, rate: int = 48000,
                 clipboard: ClipboardStore | None = None,
                 shared_clipboard: ClipboardStore | None = None):
        folder = Path(folder)
        self.lock = threading.RLock()
        if (folder / "manifest.json").exists() or (folder / "project.sqlite").exists():
            self.package = package.open_package(folder)
            is_new = False
        else:
            self.package = package.create(folder, rate)
            is_new = True
        self.package.start()
        #: This project's clipboard (WP65): ``clipboard.json`` in the project
        #: folder. Not project state (no history step); only the instance that
        #: holds the lock writes it, a read-only open keeps it in memory, and a
        #: failed write is a warning, never an error.
        #: Clipboard preview level (WP82): entry loudness by entry, the project
        #: reference by its speech tracks' content keys.
        self._entry_levels: dict[tuple, tuple[float | None, float | None]] = {}
        self._reference_cache: dict[tuple, tuple[float, float | None]] = {}
        self._reference_measuring: set[tuple] = set()
        self.clipboard = clipboard or ClipboardStore(
            project_path(self.package.path), writable=not self.read_only, soft=True)
        #: The shared store (WP65): the per-user file. It holds what the user
        #: marked as worth sharing, and the old history of projects that have
        #: not opened since it was moved into projects.
        self.shared_clipboard = shared_clipboard or ClipboardStore()
        self._move_shared_history()
        self._reconcile_shared_flags()
        self.jobs = Jobs()
        #: Folder of the last "Export all tracks" this run made, for Show in Finder.
        self.last_export_folder: str | None = None
        #: The newest automixer log (kept or failed), for "Show log" in the notice.
        self.last_automix_log: str | None = None
        #: The newest automixer run's printed lines, for the live log viewer. Kept after
        #: the run until the next one starts. Own lock: a poll never waits on the session.
        self._live_lock = threading.Lock()
        self._live_lines: deque[str] = deque(maxlen=AUTOMIX_LIVE_LINES)
        self._live_running = False
        self._live_started: str | None = None
        #: The Auto-Silence live preview (``silence_measure``): the latest
        #: measure of the speech audio, kept in memory (about 5 bytes per hop
        #: per mic: 2.7 MB for 45 minutes x 4) and valid only while its key
        #: (``analysis.silence_key``) is the project's. A stale one is dropped
        #: the next time the preview asks, not on every edit: working the key
        #: out after each edit would cost the edit budget for nothing.
        #: ``_silence_job``: (key, job id) of the measure in progress.
        self._silence_lock = threading.Lock()
        self._silence_measure: analysis.SilenceMeasure | None = None
        self._silence_job: tuple[str, str] | None = None
        #: The numbers of the latest Set music level, for the UI's notice.
        self.last_music_level: dict | None = None
        self.last_block_level: dict | None = None
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
        #: resume.json in the project folder (not project state; docs/FORMAT.md).
        self.resume = ResumeWriter(self.package.path, enabled=not self.read_only)
        if not is_new and not self.read_only:
            self.history.session_opened()
        # Background transcription (WP79): finished results are taken in at open and
        # then as they arrive; ``_finished_jobs`` keeps what this run added, to list.
        self._notices: list[dict] = []
        self._notice_lock = threading.Lock()
        self._ingest_lock = threading.Lock()
        self._finished_jobs: dict[str, dict] = {}
        self._watch_stop = threading.Event()
        self.poll_background()
        self._watcher = threading.Thread(target=self._watch_background, daemon=True,
                                         name="kuulas-bgjobs")
        self._watcher.start()

    # -- the project -------------------------------------------------------

    @property
    def state(self) -> Project:
        with self.lock:
            return self.history.state

    def _scoped(self, name: str, args: dict) -> tuple[dict, dict]:
        """``(args for the op, args to record)``. WP83: an edit touches what it
        names, plus the members of the clips' explicit groups; sync partners are
        never added, and the retired ``group_editing`` switch is dropped if an
        older page still sends it. A range op with no tracks acts on all tracks."""
        rest = {k: v for k, v in args.items() if k != "group_editing"}
        if name in GROUPED_OPS and rest.get("clip_ids") is not None:
            rest["clip_ids"] = edit_scope.expand_clips(self.history.state,
                                                       rest["clip_ids"])
        elif name in RANGE_OPS:
            try:
                rest["track_ids"] = edit_scope.range_tracks(self.history.state,
                                                            rest.get("track_ids"))
            except KeyError as e:
                raise ops.EditError("error.edit.no_track", track_id=e.args[0]) from None
        return rest, rest

    def sync_state(self, clip_id: str) -> sync_state.SyncState:
        with self.lock:
            return sync_state.sync_state(self.history.state, clip_id)

    def sync_overview(self) -> list[dict]:
        """Every clip that is drifting or free, in timeline order, with its
        ``state`` and ``offset`` (frames): what the timeline's badges draw.
        Memoized on the edit state and the sync groups, so the page can ask after
        every edit."""
        with self.lock:
            key = self._view_key(self.history.edit_hash, self.history.material_head)
            def compute() -> list[dict]:
                return [asdict(d) for d in sync_state.overview(self.history.state)]

            return list(self._memo("sync_overview", key, compute, 120))

    def sync_preview(self, name: str, args: dict | None = None) -> dict:
        """What a sync command that MOVES clips would do, without doing it (owner,
        2026-10-19: sync asks first). ``name``: ``resync``, ``resync_from`` or
        ``send_home``, with the command's own args. It runs the same pure op on the
        current state and diffs, so the listed shifts are the real ones. ``moves``: one
        row per clip that would change, in timeline order: ``clip_id``, ``track`` (its
        track's name now), ``name`` (the clip's own, may be empty), ``shift`` (frames,
        signed) and ``to_track`` for a clip that would change track. Clips that stay are
        not listed. Changes nothing, no history step."""
        args = args or {}
        with self.lock:
            before = self.history.state
            if name == "send_home":
                ids = _resync_ids(before, args)
                new = ops.send_home(before, ids)
                outcome = {"skipped": 0, "anchor": ""}
            elif name in ("resync", "resync_from"):
                pick = _resync_from_ids if name == "resync_from" else _resync_ids
                ids = pick(before, args)
                new = ops.resync(before, ids)
                outcome = _sync_outcome(before, ids, new)
            else:
                raise ops.EditError("error.edit.unknown", name=name)
            moves = []
            for track in before.tracks:
                for clip in track.clips:
                    if clip.id not in ids:
                        continue
                    try:
                        after, after_track = new.clip_and_track(clip.id)
                    except KeyError:  # overwritten by a clip that came home
                        continue
                    shift = after.start - clip.start
                    if shift == 0 and after_track.id == track.id:
                        continue
                    changed = after_track.id != track.id
                    moves.append({
                        "clip_id": clip.id, "track": track.name, "name": clip.name,
                        "start": clip.start, "shift": shift,
                        "to_track": after_track.name if changed else None})
            moves.sort(key=lambda m: (m["start"], m["clip_id"]))
            result = {"command": name, "rate": before.rate, "moves": moves,
                      "count": len(moves), "skipped_free": outcome["skipped"],
                      "anchor": outcome["anchor"]}
            if moves:
                return {**result, "kind": "move"}
            if name == "send_home":
                message = t("toast.sync.nothing_home")
                return {**result, "kind": "nothing", "message": message}
            return {**result, "kind": "nothing", "message": outcome["message"]}

    def sync_anchors(self) -> list[dict]:
        """The anchor pieces of every sync group (clips of the group's main
        media): what the timeline tags and what drift is measured against."""
        with self.lock:
            p = self.history.state
            return [{"clip_id": c.id, "track_id": tr.id, "name": tr.name, "group": g.id}
                    for g in p.sync_groups for tr in p.tracks for c in tr.clips
                    if c.media == g.main]

    def partners_of(self, clip_ids: list[str]) -> dict[str, list[str]]:
        """Clip id -> its sync partners' ids (free clips are no one's partner).
        Knowledge only: no edit takes a partner along (WP83)."""
        with self.lock:
            state = self.history.state
            return {cid: [c.id for c in edit_scope.partners(state, None, cid)]
                    for cid in clip_ids}

    def drift_list(self, with_cause: bool = False) -> list[dict]:
        """Clips in undecided drift, in timeline order: the markers panel's
        list (] and [ step through it). Free clips are not on it. ``with_cause``
        adds ``sync_cause`` to each (it reads history, so it costs more)."""
        out = []
        for d in self.sync_overview():
            if d["state"] != sync_state.DRIFT:
                continue
            row = {k: d[k] for k in ("clip_id", "track_id", "start", "offset")}
            if with_cause:
                row["cause"] = self.sync_cause(d["clip_id"])
            out.append(row)
        return out

    def sync_cause(self, clip_id: str) -> dict | None:
        """The history step that put ``clip_id`` out of sync, read from history:
        ``{"label", "op", "track_id", "created"}``, or None when the clip is not
        drifting (or the step is more than ``CAUSE_STEPS`` back)."""
        with self.lock:
            steps = self.history.recent(CAUSE_STEPS)
            index = sync_state.cause([p for _, p in steps], clip_id)
            if index is None:
                return None
            row, project = steps[index]
            return {"label": row["label"], "op": (row["op"] or {}).get("name"),
                    "track_id": project.clip_and_track(clip_id)[1].id,
                    "created": row["created_utc"]}

    #: What the last ``resync`` / ``resync_from`` did, for the page's message.
    last_resync: dict | None = None

    @property
    def read_only(self) -> bool:
        return self.package.read_only

    def flush_view(self, playhead: int | None = None) -> None:
        """Save the last view the page sent, with ``playhead`` as the cursor, to
        the per-user view memory and to resume.json at once. For a window that
        closes without a last word from the page (it may be playing: the page
        saves the cursor only every 5 s). Nothing sent this session, nothing
        written; never raises."""
        view = self.resume.view
        if view is None:
            return
        if playhead is not None:
            view["playhead"] = int(playhead)
        view["saved_at"] = now_iso()
        with contextlib.suppress(ValueError, OSError):  # ViewMemoryError is a ValueError
            ViewMemory().put(self.package.manifest["id"], view)
        self.resume.close(playhead=playhead)

    def close(self) -> None:
        self._watch_stop.set()
        self._watcher.join(5)
        # This project's analysis worker, running or waiting, ends now.
        folder = getattr(self.store, "folder", None)
        if folder is not None:
            offload.MANAGER.cancel_owner(str(folder))
        self.jobs.close()
        self.resume.close()  # while the lock is still ours
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
            applied, recorded = self._scoped(name, args)
            new = ops.apply(self.history.state, name, applied)
            material = None
            if name == "replace_clip_media":
                # Transcripts are keyed by media id: the edited copy takes the old
                # media's words, in the same undo step. Files are not touched.
                material = self.history.carry_transcript(
                    applied["media_id"], applied["new_media_id"],
                    new.media_item(applied["new_media_id"]).frames)
            self.history.commit(label or name, new,
                                coalesce or _coalesce_key(name, args),
                                op={"name": name, "args": recorded},
                                material=material)
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

    def duck_music(self, measured: dict | None = None) -> Project:
        """Measure outside the lock, then write the music duck curve in one step."""
        if measured is None:
            with self.lock:
                snapshot = self.history.state
            intervals = offload.call("anyone_talking_intervals", snapshot, self.store)
            measured = {"key": analysis.duck_key(snapshot), "intervals": intervals}
        return self.command("duck_music", {"measured": measured})

    def duck_music_measure(self, args: dict | None = None) -> list[str]:
        """Queue cancellable speech analysis for the selected music-duck style."""
        args = args or {}
        style = args.get("style", "gaps")
        if style not in {"gaps", "sidechain"}:
            raise ops.EditError("error.edit.bad_arguments", name="duck_music",
                                detail="style")
        sidechain = None
        if style == "sidechain":
            try:
                sidechain = {
                    "threshold_db": float(args.get("threshold_db", -30.0)),
                    "ratio": float(args.get("ratio", 8.0)),
                    "attack_s": float(args.get("attack_s", 0.05)),
                    "release_s": float(args.get("release_s", 0.3)),
                }
            except (TypeError, ValueError):
                raise ops.EditError("error.edit.bad_arguments", name="duck_music",
                                    detail="sidechain options") from None
            if not (-60 <= sidechain["threshold_db"] <= 0
                    and 1 <= sidechain["ratio"] <= 20
                    and 0.001 <= sidechain["attack_s"] <= 0.5
                    and 0.01 <= sidechain["release_s"] <= 2.0):
                raise ops.EditError("error.edit.bad_arguments", name="duck_music",
                                    detail="sidechain options")
        with self.lock:
            snapshot = self.history.state

        def run(progress):
            progress(0.0, "", True)
            if style == "sidechain":
                measured = offload.call(
                    "duck_sidechain", snapshot, self.store,
                    **sidechain,
                    cancel=progress.cancelled_event,
                )
                measured["style"] = "sidechain"
                return measured
            intervals = offload.call("anyone_talking_intervals", snapshot, self.store,
                                     cancel=progress.cancelled_event)
            if progress.cancelled:
                raise JobCancelledError
            return {"key": analysis.duck_key(snapshot), "intervals": intervals}

        return [self.jobs.submit("duck_music", t("job.duck_music"), run,
                                 keep_result=True)]

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

        measured_results = priority.gated_map(_measure, clips_to_measure, max_workers)

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
                "source_name": entry.source_name or Path(entry.source_project).stem}

    def _move_shared_history(self) -> None:
        """Once per entry (WP65 step 3): the old per-user history becomes the
        shared store, and the entries this project made move into its own
        clipboard. Entries marked shared stay (they are the shared copies), as
        do those of other or unknown projects, until their project opens.

        Copy first, remove second: if the project's file cannot be written
        nothing leaves the shared one, and a shared file that cannot be written
        back only leaves duplicates that the next open clears. Idempotent. A
        read-only open moves nothing (it may not write the project). Never
        raises: the clipboard must not stop a project opening."""
        if self.read_only:
            return
        try:
            mine = [e for e in self.shared_clipboard.load().entries()
                    if not e.shared and clipboard_link.same_folder(
                        e.source_project, self.package.path)]
            if not mine:
                return
            self.clipboard.update(lambda h: h.merge(mine))
            if self.clipboard.write_error:
                return
            moved = [e.id for e in mine]
            self.shared_clipboard.update(lambda h: h.remove(moved))
        except OSError as e:
            log.warning(t("log.clipboard.move_failed", error=str(e)))

    def _reconcile_shared_flags(self) -> None:
        """The shared store is what says whether an entry is shared: an own
        entry flagged shared that the shared store no longer has (unshared from
        another project's Shared view, or the file was lost) loses its flag.
        Same rules as ``_move_shared_history``: not read-only, never raises."""
        if self.read_only:
            return
        try:
            flagged = [e.id for e in self.clipboard.load().entries() if e.shared]
            if not flagged:
                return
            have = {e.id for e in self.shared_clipboard.load().entries()}
            stale = [i for i in flagged if i not in have]
            if stale:
                def clear(history):
                    for entry_id in stale:
                        history.set_shared(entry_id, False)

                self.clipboard.update(clear)
        except OSError as e:
            log.warning(t("log.clipboard.move_failed", error=str(e)))

    def _describe(self, entry: Entry) -> Entry:
        """``entry`` with what only the session knows (WP65): this project's
        folder, name and manifest id, and the transcript words inside the
        copied stretch. Reads the transcripts, so a project without any gives
        an empty text."""
        try:
            text = entry_text(self.state, entry, self.transcripts())
        except (KeyError, ValueError, TypeError) as e:
            # The text is a convenience for searching; it never stops a copy.
            log.warning(t("log.clipboard.text_failed", error=str(e)))
            text = ""
        return replace(entry, source_project=str(self.package.path),
                       source_name=Path(self.package.path).stem,
                       source_id=str(self.package.manifest.get("id", "")), text=text)

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

    def clipboard_shared(self) -> list[dict]:
        """The shared store, newest first, in the same view as ``clipboard_list``
        (the missing-here count is against this project)."""
        project = self.state
        return [self._entry_view(e, project)
                for e in self.shared_clipboard.load().entries()]

    def clipboard_share(self, entry_id: str, shared: bool = True) -> None:
        """Mark one of this project's entries as worth sharing, or take it back.

        Marking puts a copy (same id, ``shared`` true) into the shared store and
        flags the own entry; unmarking removes the shared copy and clears the
        flag. The id may also be one that only the shared store has (another
        project's): unmarking then removes it from the shared store, and that
        project's own flag is cleaned up when it opens. The shared store is
        written first, so a failure leaves the flag unset rather than set for
        nothing. Not project state: no undo step."""
        own = self.clipboard.load().get(entry_id)
        try:
            if shared:
                if own is None:
                    raise NoSuchEntryError("error.clipboard.no_entry", entry_id=entry_id)
                copy = replace(own, shared=True)
                self.shared_clipboard.update(lambda h: h.put(copy))
            else:
                known = self.shared_clipboard.update(
                    lambda h: h.remove([entry_id]) > 0)
                if own is None and not known:
                    raise NoSuchEntryError("error.clipboard.no_entry", entry_id=entry_id)
        except OSError as e:
            raise ops.EditError("error.clipboard.write_failed", error=str(e)) from None
        if own is not None:
            self._change_history(entry_id, lambda h: h.set_shared(entry_id, shared))

    def clipboard_projects(self) -> list[dict]:
        """The recent projects other than this one, with how many clipboard
        entries each has (read now, read-only): the desktop's recents list, so
        headless, or with none remembered, it is empty."""
        from . import desktop  # noqa: PLC0415  (heavy, and only the desktop has recents)

        recents = desktop.load_recents(desktop.recents_file())
        return clipboard_browse.recent_projects(recents, self.package.path)

    def clipboard_project(self, path: str) -> dict:
        """Another project's clipboard, read-only: ``{project: {name, path},
        entries: [view...]}``. ``path`` must be a kuulas project folder
        (``clipboard_browse.project_folder``); a missing or damaged
        ``clipboard.json`` is an empty list."""
        folder = clipboard_browse.project_folder(path)
        project = self.state
        return {"project": {"name": folder.stem, "path": str(folder)},
                "entries": [self._entry_view(e, project)
                            for e in clipboard_browse.read_entries(folder)]}

    def clipboard_adopt(self, entry: object, from_project: str = "") -> dict:
        """Copy an entry from the shared store or another project into THIS
        project's clipboard (new id, ``adopted_from`` set) and return its view;
        the normal paste then works on it. ``entry`` is the view the API listed.
        The original is untouched."""
        parsed = entry_from_view(entry)
        mine = adopted_copy(parsed, from_project=str(from_project or ""))
        self.clipboard.update(lambda h: h.add(mine))
        return self._entry_view(mine, self.state)

    def clipboard_preview(self, entry_id: str, limit: bool = True):
        """``(temporary project or None, missing media count, gain dB)`` for
        playing an entry without changing this project (``clipboard_preview``).

        With ``limit`` the temporary project carries an attenuation (its master
        gain, 0 or less) that brings the entry down to the project's own level
        (WP82, ``preview_level``); nothing is ever boosted, and neither the
        pasted audio nor the project's mix changes. The measuring reads only the
        entry's and the speech tracks' own audio, from a snapshot, off the lock.
        """
        snapshot = self.state
        entry = self._entry(entry_id)
        project, missing = preview_project(snapshot, entry)
        if project is None or not limit:
            return project, len(missing), 0.0
        cache_root = getattr(self.store, "cache_root", None)
        reference, project_peak = self._preview_reference(snapshot, cache_root)
        key = (entry.id, project.rate,
               tuple((t.gain_db, t.pan, t.mono) for t in project.tracks))
        if key not in self._entry_levels:
            self._entry_levels[key] = clipboard_level.entry_level(project, self.store)
        lufs, entry_peak = self._entry_levels[key]
        gain = round(preview_level.preview_gain_db(
            reference, lufs, entry_peak_db=entry_peak, project_peak_db=project_peak), 2)
        return replace(project, master_gain_db=gain), len(missing), gain

    def _preview_reference(self, snapshot: Project,
                           cache_root) -> tuple[float, float | None]:
        """The project's reference level, remembered while its speech tracks'
        audio is the same (their content keys, which fail closed)."""
        key = loudness_curve_module.speech_key(snapshot)
        if key is not None and key in self._reference_cache:
            return self._reference_cache[key]
        if snapshot.length > INLINE_REFERENCE_S * snapshot.rate:
            # A long recording takes seconds to minutes to measure, and while it
            # plays the background analysis is held back, so it is never cached
            # yet when the user clicks Play on a chip (owner, 2026-10-21: the
            # preview came "VERY MUCH LATER"). Start now with the conservative
            # default and measure in the background for the next click.
            self._measure_reference_later(snapshot, cache_root, key)
            return preview_level.reference_lufs([], None), None
        got = clipboard_level.project_reference(snapshot, self.store, cache_root)
        if key is not None:
            self._reference_cache = {key: got}
        return got

    def _measure_reference_later(self, snapshot: Project, cache_root,
                                 key: tuple | None) -> None:
        """Measure the project's reference level on a background thread (once at a
        time), remembering it under ``key`` for the next preview."""
        if key is None or key in self._reference_measuring:
            return
        self._reference_measuring.add(key)

        def measure() -> None:
            try:
                got = clipboard_level.project_reference(snapshot, self.store, cache_root)
                self._reference_cache = {key: got}
            except Exception:
                log.exception("clipboard preview reference")
            finally:
                self._reference_measuring.discard(key)

        priority.thread(measure, "kuulas-preview-reference").start()

    def clipboard_copy(self, *, clip_ids=None, start=None, end=None, track_ids=None,
                       name: str = "") -> dict:
        """Copy the clips, or the stretch ``[start, end)`` of the tracks (``None``:
        all tracks), to the clipboard. The project is not changed."""
        project = self.state
        if clip_ids is not None:
            entry = make_entry(project, clip_ids, name=name)
        elif start is None or end is None:
            raise ops.EditError("error.edit.no_selection")
        else:
            track_ids = self._range_scope(project, track_ids)
            entry = make_entry_range(project, int(start), int(end), track_ids, name=name)
        entry = self._describe(entry)
        self.clipboard.update(lambda h: h.add(entry))
        return {"entry": self._entry_view(entry, project)}

    @staticmethod
    def _range_scope(project: Project, track_ids) -> list[str]:
        """``edit_scope.range_tracks`` with an unknown track as an ``EditError``."""
        try:
            return edit_scope.range_tracks(project, track_ids)
        except KeyError as e:
            raise ops.EditError("error.edit.no_track", track_id=e.args[0]) from None

    def clipboard_cut(self, *, start: int, end: int, track_ids=None,
                      name: str = "", label: str | None = None) -> dict:
        """Cut (X): ripple-delete ``[start, end)`` and keep what went on the
        clipboard. One undo step for the removal. A copy that fails (nothing
        under the range, a full disk) is logged and reported in the result, and
        never stops the cut: the user's edit comes first."""
        return self._cut_to_clipboard("clipboard_cut", ops.cut_range, start=start,
                                      end=end, track_ids=track_ids, name=name,
                                      label=label or t("history.clipboard_cut"))

    def clipboard_lift_cut(self, *, start: int, end: int, track_ids=None,
                           name: str = "", label: str | None = None) -> dict:
        """Lift-cut (Alt+X): copy ``[start, end)`` to the clipboard and delete it, leaving
        the gap (nothing moves; one undo step restores it). Same targets and failure rule
        as ``clipboard_cut``."""
        return self._cut_to_clipboard("clipboard_lift_cut", ops.clear_range, start=start,
                                      end=end, track_ids=track_ids, name=name,
                                      label=label or t("history.clipboard_lift_cut"))

    def _cut_to_clipboard(self, op_name: str, remove: Callable, *, start: int, end: int,
                          track_ids, name: str, label: str) -> dict:
        start, end = int(start), int(end)
        with self.lock:
            project = self.history.state
            scope = self._range_scope(project, track_ids)
            entry, problem = None, None
            try:
                entry = self._describe(
                    make_entry_range(project, start, end, scope, name=name))
            except KuulasError as e:
                problem = t(e.key, **e.params)
            new = remove(project, start, end, scope)
            self.history.commit(label, new,
                                op={"name": op_name,
                                    "args": {"start": start, "end": end,
                                             "track_ids": list(scope)}})
            self._changed()
        if entry is not None:
            try:
                self.clipboard.update(lambda h, e=entry: h.add(e))
            except OSError as e:
                problem = t("error.clipboard.write_failed", error=str(e))
        if problem is None and self.clipboard.write_error:
            problem = t("error.clipboard.write_failed", error=self.clipboard.write_error)
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
                        target_tracks=None, out: int | None = None,
                        label: str | None = None) -> dict:
        """Paste an entry at frame ``at`` as one undo step; ``mode`` is
        ``insert`` (ripple) or ``overwrite`` (the default of the UI). ``out``: the
        marked Out point, ``at`` then being the In point: the paste is cut to end there.
        ``target_tracks`` maps the
        entry's track slots to track ids (``None``: the same tracks). Media
        the project lacks are reported in ``missing`` and their clips left
        out; a paste that places nothing commits nothing. An insert is a
        time-shifting edit: it ripples the target tracks only (WP83: a sync group
        is not a scope)."""
        entry = self._entry(entry_id)
        self._link_missing_media(entry)
        mapping = (None if target_tracks is None
                   else {int(slot): track for slot, track in target_tracks.items()})
        at = int(at)
        out = None if out is None else int(out)
        with self.lock:
            project = self.history.state
            plan = plan_paste(project, entry, at, mode, mapping, out=out)
            report = {"placed": len(plan.placements), "missing": list(plan.missing),
                      "entry": entry.id}
            if not plan.placements:
                return report
            landed = set(_targets(project, entry, mapping).values())
            new = apply_paste(project, entry, plan, at, landed, mode, out=out)
            self.history.commit(
                label or t("history.clipboard_paste"), new,
                op={"name": "clipboard_paste",
                    "args": {"entry_id": entry.id, "at": at, "mode": mode,
                             "target_tracks": target_tracks, "out": out}})
            self._changed()
        return report

    def clipboard_edit(self, op: str, args: dict, label: str | None = None) -> dict:
        """``/api/edit``'s door to the edits that touch the clipboard. The retired
        ``group_editing`` switch (WP83) is ignored if an older page sends it."""
        args = {k: v for k, v in args.items() if k != "group_editing"}
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

    def clipboard_clear_old(self, keep: int = 100) -> int:
        """"Clear old entries": drop this project's oldest entries beyond the
        newest ``keep`` (default 100, at least one; pinned ones stay); return
        how many went. The only way entries ever leave the clipboard except
        deleting one by hand."""
        return self.clipboard.update(lambda h: h.prune(int(keep))) or 0

    def clipboard_pin(self, entry_id: str, pinned: bool = True) -> None:
        self._change_history(entry_id, lambda h: h.pin(entry_id) if pinned
                             else h.unpin(entry_id))

    def _follow_shared(self, entry_id: str, change: Callable) -> None:
        """Apply ``change`` to the shared copy of an entry, if there is one. The
        shared copy is a convenience: a failure here is a warning, and the
        project's own entry (already changed) is what counts."""
        try:
            self.shared_clipboard.update(
                lambda h: change(h) if h.get(entry_id) is not None else None)
        except OSError as e:
            log.warning(t("log.clipboard.copy_failed", error=str(e)))

    def clipboard_rename(self, entry_id: str, name: str) -> None:
        clean = str(name).strip()[:200]
        self._change_history(entry_id, lambda h: h.rename(entry_id, clean))
        self._follow_shared(entry_id, lambda h: h.rename(entry_id, clean))

    def clipboard_delete(self, entry_id: str) -> None:
        self._change_history(entry_id, lambda h: h.delete(entry_id))
        self._follow_shared(entry_id, lambda h: h.delete(entry_id))

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
        return export_module.options("tracks", export_module.ALL_TRACKS, args or {})

    def mix_export_args(self, args: dict | None = None) -> dict:
        """The export arguments of the one-button mix export: ``export.MIX_FILE``
        (a file in ``<project> exports`` named by edit, time and version) and any
        ``format``, ``bit_depth``, ``kbps`` or ``folder`` the caller chose."""
        return export_module.options("mix", export_module.MIX_FILE, args or {})

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

    def automix_live_add(self, line: str) -> None:
        """One more line the automixer printed (any thread)."""
        with self._live_lock:
            self._live_lines.append(line)

    def automix_live(self) -> dict:
        """``{"running", "lines", "started"}`` of the newest automixer run; empty before
        any run, and the last run's lines stay until the next one starts."""
        with self._live_lock:
            return {"running": self._live_running, "lines": list(self._live_lines),
                    "started": self._live_started}

    def _automix_live_state(self, running: bool, *, fresh: bool = False) -> None:
        with self._live_lock:
            if fresh:
                self._live_lines.clear()
                self._live_started = datetime.now(UTC).isoformat(timespec="seconds")
            self._live_running = running

    def automix(self, params: dict | None = None) -> list[str]:
        """Queue ONE job that mixes the edit with the automixer (WP68): stems to a
        temporary folder, the tool, the mix beside the project. ``params``:
        ``target_lufs``, ``ad_spot``, ``ad_duration``, ``extra_args``. Bad
        numbers and a read-only project fail now. The job's ``result`` is
        ``{"path", "name", "log", "command", "log_file", "summary"}``;
        ``last_export_folder`` becomes its
        folder."""
        params = dict(params or {})
        automix_module.validate_params(params)
        automix_module.validate_range(params)
        automix_module.check_rate(self)
        with self.lock:
            self.history._check_writable()
        settings = automix_module.load_settings()

        def run(progress):
            try:
                result = automix_module.run(
                    self, params, settings,
                    lambda fraction, message="", indeterminate=False: progress(
                        fraction, message, indeterminate),
                    progress.cancelled_event, live=self.automix_live_add,
                    eta=progress.set_eta, detail=progress.set_detail)
            except automix_module.AutomixError as e:
                self.last_automix_log = e.params.get("log_file") or self.last_automix_log
                raise
            finally:
                self._automix_live_state(False)
            self.last_automix_log = result.get("log_file") or self.last_automix_log
            self.last_export_folder = str(Path(result["path"]).parent)
            self.note_render(result)
            return result

        self._automix_live_state(True, fresh=True)
        return [self.jobs.submit("automix", t("job.automix"), run, keep_result=True)]

    def note_render(self, result: dict) -> None:
        """Remember an automix run's mix (whole or a range) as ``mix_done.render``, ONE
        undo step that changes no sound (``render_listen.entry``; docs/FORMAT.md), so it
        can be listened to while the edit still sounds as it did. A newer render replaces
        the record, never a file. Never raises: the mix is on disk either way, and a
        read-only or vanished project only loses the record (logged)."""
        at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
        found = render_listen.entry(result, at)
        if found is None:
            log.warning("automix result without what listening needs: %s",
                        result.get("path"))
            return
        try:
            with self.lock:
                state = self.history.state
                new = replace(state, mix_done={**state.mix_done, "render": found})
                self._commit(t("history.note_render", name=found["name"]), new,
                             "note_render", {"name": found["name"],
                                             "range": found["range"]})
        except Exception:  # the mix exists; only the record is lost
            log.exception("could not remember the render %s", found["path"])

    def auto_silence_preview(self, args: dict | None = None) -> list[str]:
        """Queue ONE job that says what Auto-Silence with these options WOULD
        close, per speech track, without changing anything (no history step).
        The session lock is held only to take the snapshot; the analysis runs
        on the snapshot in the job (ground rule 14). The job's ``result`` is
        ``{"tracks": [{track_id, name, close_s, stretches, now_s}], "options"}``.
        Bad options fail now."""
        args = dict(args or {})
        options = silence_options.parse(args)
        track_ids = args.get("track_ids")
        with self.lock:
            snapshot = self.history.state

        def run(progress):
            progress(0.0, "", True)
            # In the analysis worker (offload): its own GIL, stopped while playing.
            rows = offload.call("preview_silence", snapshot, self.store, options,
                                track_ids, cancel=progress.cancelled_event)
            if progress.cancelled:
                raise JobCancelledError
            return {"tracks": rows, "options": options.as_dict()}

        return [self.jobs.submit("auto_silence_preview",
                                 t("job.auto_silence_preview"), run, keep_result=True)]

    # -- the Auto-Silence live preview -----------------------------------------
    #
    # Two stages (analysis: measure once, decide per options). The measure is a
    # background job in the analysis worker, one track per call so the job can
    # say how far it is and memory stays at one track's audio; the decision runs
    # here per slider move on the kept measure, without the session lock.

    def _silence_now(self) -> tuple[Project, str]:
        with self.lock:
            state = self.history.state
        return state, analysis.silence_key(state)

    def _silence_valid(self, key: str) -> analysis.SilenceMeasure | None:
        """The kept measure if it is of ``key``; a stale one is dropped."""
        with self._silence_lock:
            measure = self._silence_measure
            if measure is not None and measure.key != key:
                self._silence_measure = measure = None
            return measure

    def silence_measure(self) -> dict:
        """Make sure there is a measure of the speech audio as it is now:
        ``{"ready": True, "jobs": [], "key"}`` when one is kept, else the id of
        the job that measures it (a running one for the same audio is reused,
        not doubled). The job's ``result`` is ``{key, tracks, bytes}``."""
        state, key = self._silence_now()
        if self._silence_valid(key) is not None:
            return {"ready": True, "jobs": [], "key": key}
        with self._silence_lock:
            running = self._silence_job
            if running is not None and running[0] == key and self._job_live(running[1]):
                return {"ready": False, "jobs": [running[1]], "key": key}
            ids = analysis.silence_measured_ids(state)

            def run(progress):
                measure = self._silence_measure_now(state, progress)
                return {"key": measure.key, "tracks": len(ids), "bytes": measure.nbytes}

            job_id = self.jobs.submit("silence_measure", t("job.silence_measure"), run,
                                      keep_result=True)
            self._silence_job = (key, job_id)
        return {"ready": False, "jobs": [job_id], "key": key}

    def _silence_measure_now(self, state: Project, progress,
                             share: float = 1.0) -> analysis.SilenceMeasure:
        """Measure ``state``'s speech in the analysis worker, one track per call
        (progress up to ``share``), and keep it as the live preview's measure."""
        ids = analysis.silence_measured_ids(state)
        names = {tr.id: tr.name for tr in state.tracks}
        levels = {}
        for i, track_id in enumerate(ids):
            progress(share * i / len(ids), t("job.silence_measure_track",
                                             name=names[track_id], n=i + 1,
                                             total=len(ids)))
            levels[track_id] = offload.call(
                "silence_track_levels", state, self.store, track_id,
                cancel=progress.cancelled_event)
            if progress.cancelled:
                raise JobCancelledError
        measure = analysis.assemble_measure(state, levels)
        with self._silence_lock:
            self._silence_measure = measure
        return measure

    def silence_learn(self, args: dict | None = None) -> dict:
        """Track > Auto > Calculate Auto-Silence values from the selection: queue
        ONE job that learns the Auto-Silence Sensitivity from the selected clips
        (muted ones are "closed", the others "open"; ``silence_learn``) and
        commits nothing. ``args``: ``clip_ids`` and the panel's current options
        (what cannot be learned stays as they have it). The speech is measured
        first when no measure of it is kept, and the measure is kept, so the
        panel opens on it at once. The job's ``result`` is
        ``silence_learn.suggestion``'s plus ``key``. A selection with no clip of
        a speech track is refused now."""
        args = dict(args or {})
        options = silence_options.parse(args)
        clip_ids = [str(c) for c in args.get("clip_ids") or ()]
        state, key = self._silence_now()
        if not silence_learn.examples(state, clip_ids):
            raise ops.EditError("error.silence.learn_no_selection")

        def run(progress):
            progress(0.0, "", True)
            measure = self._silence_valid(key) or self._silence_measure_now(
                state, progress, share=0.8)
            progress(0.8, t("job.silence_learn"))
            found = offload.call("silence_learn", state, self.store, clip_ids,
                                 cancel=progress.cancelled_event)
            if progress.cancelled:
                raise JobCancelledError
            floors = {tid: lv.floor for tid, lv in measure.levels.items()}
            out = silence_learn.suggestion(state, found, floors, options)
            for row in out["tracks"]:
                # The numbers are silencelearn's taste values: the log is where a
                # real session shows what each track got.
                log.info(t("log.silence.learn", name=row["name"], code=row["code"],
                           threshold=row["threshold"], floor=row["floor"],
                           note=row["note"]))
            return {**out, "key": key}

        return {"jobs": [self.jobs.submit("silence_learn", t("job.silence_learn"), run,
                                          keep_result=True)]}

    def _job_live(self, job_id: str) -> bool:
        return any(j["id"] == job_id and j["state"] in ("queued", "running")
                   for j in self.jobs.list())

    def _silence_decide(self, args: dict | None) -> tuple:
        """``(state, key, options, measure, ranges, gates)``: the decision on
        the kept measure for the state now, outside the session lock."""
        args = dict(args or {})
        options = silence_options.parse(args)
        state, key = self._silence_now()
        measure = self._silence_valid(key)
        if measure is None:
            raise SilenceNotMeasuredError("error.silence.not_measured")
        gates = {tr.id: tr.gate for tr in state.tracks}
        ranges = analysis.without_ungated(
            state, analysis.silence_ranges_from(measure, options, gates))
        return state, key, options, measure, ranges, gates

    def silence_preview_ranges(self, args: dict | None = None) -> dict:
        """What Auto-Silence with these options WOULD close, decided in this
        process from the kept measure in tens of milliseconds, without the
        session lock: ``{"tracks": [{track_id, name, ranges, close_s,
        stretches, total_s, now_s}], "key", "options"}``. No history step.
        ``SilenceNotMeasuredError`` when there is no valid measure."""
        _state, key, options, measure, ranges, gates = self._silence_decide(args)
        return {"tracks": analysis.silence_rows(measure, ranges, gates), "key": key,
                "options": options.as_dict()}

    def silence_accept(self, args: dict | None = None) -> Project:
        """Commit what the preview with these options shows, as ONE undo step
        (the Auto-Silence step). ``args["key"]`` (the preview's) must still be
        the audio's; the decision runs again, here, so what is committed is
        what these options give on the audio as it is now."""
        args = dict(args or {})
        want = args.get("key")
        if want is not None and want != self._silence_now()[1]:
            raise SilenceStaleError("error.silence.stale")
        state, key, options, _measure, ranges, _gates = self._silence_decide(args)
        if want is not None and want != key:
            raise SilenceStaleError("error.silence.stale")
        track_ids = args.get("track_ids")
        with self.lock:
            if self.history.state is not state:
                # An edit came in meanwhile: decide again on what is there now.
                if analysis.silence_key(self.history.state) != key:
                    raise SilenceStaleError("error.silence.stale")
                state = self.history.state
                measure = self._silence_valid(key)
                if measure is None:
                    raise SilenceNotMeasuredError("error.silence.not_measured")
                ranges = analysis.without_ungated(state, analysis.silence_ranges_from(
                    measure, options, {tr.id: tr.gate for tr in state.tracks}))
            new = analysis.apply_silence(state, ranges, track_ids)
            recorded = {**options.as_dict(),
                        **({"track_ids": list(track_ids)} if track_ids else {})}
            return self._commit(t("history.auto_silence"), new, "auto_silence", recorded)

    def music_level_measure(self, args: dict | None = None) -> list[str]:
        """Queue ONE job that measures what Set music level needs (the speech
        while anyone speaks, the beds' loudest 3 s) and changes nothing. The
        lock is held only for the snapshot; the measuring runs in the analysis
        worker (ground rule 14). The job's ``result`` is ``music_level.measure``'s
        answer plus ``was_db`` (where the beds sit against the speech now); a
        project without music or speech completes with its ``reason``."""
        mode = music_level.parse_mode((args or {}).get("mode"))
        with self.lock:
            snapshot = self.history.state

        def run(progress):
            progress(0.0, "", True)
            measured = offload.call("music_level", snapshot, self.store, mode,
                                    cancel=progress.cancelled_event)
            if progress.cancelled:
                raise JobCancelledError
            return {**measured, "was_db": music_level.distance(snapshot, measured)}

        return [self.jobs.submit("music_level", t("job.music_level"), run,
                                 keep_result=True)]

    def set_music_level(self, args: dict) -> Project:
        """Set music level as ONE undo step: each music track's ``gain_db`` so the
        beds' loudest moment sits ``offset_db`` against the speech, and
        ``mix_done["bed_level"]`` saying so. ``measured`` (the job's result) is
        used when it still describes the edit (same content key), else refused
        as stale; without it the edit is measured here, off the lock."""
        offset = music_level.parse_offset(args.get("offset_db"))
        measured = args.get("measured")
        if measured is not None and not isinstance(measured, dict):
            raise ops.EditError("error.edit.bad_arguments", name="set_music_level",
                                detail="measured")
        if measured is None:
            mode = music_level.parse_mode(args.get("mode"))
            with self.lock:
                snapshot = self.history.state
            measured = offload.call("music_level", snapshot, self.store, mode)
        music_level.check(measured)
        with self.lock:
            state = self.history.state
            mode = music_level.parse_mode(measured.get("mode"))
            try:
                current = music_level.key(state, mode)
            except caches.CacheKeyError:
                current = None
            if current is None or current != measured.get("key"):
                raise ops.EditError("error.music_level.stale")
            plan = music_level.solve(measured, offset)
            was = music_level.distance(state, measured)
            new = state
            for track_id, gain in plan.gains.items():
                new = ops.set_track(new, track_id, gain_db=gain)
            entry = music_level.record(
                measured, offset, plan,
                at=datetime.now(UTC).astimezone().isoformat(timespec="seconds"))
            new = replace(new, mix_done={**new.mix_done, "bed_level": entry})
            self.last_music_level = {
                "offset_db": offset, "was_db": was,
                "speech_lufs": measured["speech_lufs"],
                "bed_lufs": measured["bed_lufs"], "change_db": plan.change_db,
                "gains": dict(plan.gains), "clamped": list(plan.clamped),
                "text": t("ui.music_level.done", now=_against(offset), was=_against(was))}
            label = t("history.set_music_level", now=_against(offset), was=_against(was))
            recorded = {"offset_db": offset, "mode": mode,
                        "speech_lufs": measured["speech_lufs"],
                        "bed_lufs": measured["bed_lufs"], "was_db": was,
                        "gains": dict(plan.gains)}
            return self._commit(label, new, "set_music_level", recorded)

    def block_level_measure(self, args: dict | None = None) -> list[str]:
        """Queue ONE job that measures what Level blocks needs (each speaker's
        blocks, their gains and the loud spots) and changes nothing. The lock is
        held only for the snapshot; the measuring runs in the analysis worker
        (ground rule 14), cancellable. The job's ``result`` is
        ``block_level.measure``'s answer. ``args`` is the route's body (none
        are read yet)."""
        del args
        with self.lock:
            snapshot = self.history.state

        def run(progress):
            progress(0.0, "", True)
            measured = offload.call("block_level", snapshot, self.store,
                                    cancel=progress.cancelled_event)
            if progress.cancelled:
                raise JobCancelledError
            return measured

        return [self.jobs.submit("block_level", t("job.block_level"), run,
                                 keep_result=True)]

    def level_blocks(self, args: dict) -> Project:
        """Level blocks as ONE undo step: the clips of each speaker's tracks are
        split in the pauses and the blocks' gains added to their ``gain_db``
        (``block_level.apply``), plus ``mix_done["block_level"]`` while nothing
        changed was left out. ``measured`` (the job's result) is used when it
        still describes the edit (same content key), else refused as stale;
        without it the edit is measured here, off the lock. ``skip``: block ids
        to leave alone; ``markers``: a marker at each loud spot."""
        measured = args.get("measured")
        skip = args.get("skip") or []
        if not isinstance(skip, list):
            raise ops.EditError("error.edit.bad_arguments", name="level_blocks",
                                detail="skip")
        if measured is None:
            with self.lock:
                snapshot = self.history.state
            measured = offload.call("block_level", snapshot, self.store)
        block_level.check(measured)
        with self.lock:
            state = self.history.state
            try:
                current = block_level.key(state)
            except caches.CacheKeyError:
                current = None
            if current is None or current != measured.get("key"):
                raise ops.EditError("error.block_level.stale")
            new, report = block_level.apply(state, measured, skip,
                                            bool(args.get("markers")))
            at = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
            new = block_level.with_record(new, report, at)
            text = block_level.summary(report)
            self.last_block_level = {
                "blocks": report.blocks, "left_out": report.left_out,
                "tracks": report.tracks, "clamped": report.clamped,
                "markers": report.markers, "text": text}
            recorded = {"blocks": report.blocks, "tracks": report.tracks,
                        "markers": report.markers, "skip": [str(x) for x in skip]}
            return self._commit(text, new, "level_blocks", recorded)

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

    def export_settings(self) -> dict:
        """What the export dialog starts from: the remembered settings of the mix and
        of the track export (``None`` before the first), the folder used last (or the
        default), and the name of the open edit."""
        with self.lock:
            h = self.history
            saved = h.meta_json("export", {})
            edit = next((e["name"] for e in h.edits() if e["id"] == h.edit), h.edit)
        return {"mix": saved.get("settings", {}).get("mix"),
                "tracks": saved.get("settings", {}).get("tracks"),
                **self.export_folder_hint(), "edit": edit,
                "project": str(self.package.path), "title": self.export_title()}

    def export_title(self) -> str:
        """What exported files are called: the project, then the edit unless it
        is the main one (``export_names.title``)."""
        with self.lock:
            h = self.history
            edit = next((e["name"] for e in h.edits() if e["id"] == h.edit), h.edit)
            return export_names.title(self.package.path.stem, h.edit, edit)

    def download_name(self, what: str) -> str:
        """The file name of a download ("chapters.txt"): ``<title> chapters.txt``."""
        return f"{self.export_title()} {what}"

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
        # The UI asks for this by itself after edits: background work, so the
        # analysis worker is stopped while audio plays (docs/PLAYBACK-PRIORITY.md).
        with priority.background():
            return offload.call("project_curves", state, self.store,
                                getattr(self.store, "cache_root", None))

    def send_copy_plan(self) -> dict:
        """What each audio choice of File > Send a copy… would carry."""
        with self.lock:
            state = self.history.state
        return send_copy_module.plan(self.store, state)

    def send_copy(self, folder: str, media: str = "used") -> dict:
        """File > Send a copy… (WP32): write a copy of the project into ``folder`` with
        ``media`` = none | used | all. This history gets a ``sent`` checkpoint first (when
        this window may write), so the step that was sent can be found again."""
        new_copy = send_copy_module.new_copy_id()

        def freeze(target: Path) -> tuple[Project, dict]:
            with self.lock:
                if not self.read_only:
                    self.history.checkpoint(
                        t("history.sent_copy", media=t(f"send_copy.{media}")),
                        "sent", copy=new_copy)
                package.backup_to(self.package.db_path, target)
                return self.history.state, dict(self.package.manifest)

        return send_copy_module.make(self.store, freeze, self.package.path.stem, folder,
                                     media, new_copy)

    def _media_line(self, media_id: str) -> dict:
        meta = self.store.meta(media_id)
        return {"id": media_id, "name": meta["name"], "size": meta["linked_size"]}

    def media_status(self) -> dict:
        """What "Locate media…" shows before a folder is chosen: the linked media whose
        file is gone, and the media that hold only the parts a copy carried."""
        partial = []
        for media_id in self.store.partial_ids():
            info = self.store.partial_info(media_id) or {}
            partial.append({
                "id": media_id, "name": self.store.meta(media_id)["name"],
                "can_complete": bool(info.get("source_size"))})
        # A missing media no clip uses any more (relinked to an edited copy) is not
        # asked for; undo brings the clips, and so the entry, back.
        used = {c.media for tr in self.history.state.tracks for c in tr.clips}
        return {"missing": [self._media_line(m) for m in self.store.missing()
                            if m in used],
                "partial": partial}

    def locate_media(self, folder: str) -> dict:
        """File > Locate media… (WP39): look under ``folder`` for the missing media,
        and for the whole files of partial copies, by SHA-256 (a file of the same size
        and another content is never taken). Not an edit: nothing is committed.
        Returns ``{"found": [{id, name, path}], "still_missing": [...],
        "partial": [...]}``, the last two as in ``media_status``."""
        if (
            not isinstance(folder, str)
            or not folder.strip()
            or "\0" in folder
            or len(folder) > 4096
        ):
            raise MediaError("error.locate.no_folder", folder=str(folder or "")[:200])
        try:
            target = Path(folder).expanduser()
            if not target.is_dir():
                raise MediaError("error.locate.no_folder", folder=str(folder)[:200])
        except (OSError, RuntimeError):
            raise MediaError("error.locate.no_folder", folder=str(folder)[:200]) from None
        before = self.media_status()
        completable = any(p["can_complete"] for p in before["partial"])
        if not before["missing"] and not completable:
            return {"found": [], "still_missing": [], "partial": before["partial"]}
        if self.read_only:
            raise MediaError("error.locate.read_only")
        found = self.store.relink(Path(folder).expanduser())
        log.info(t("log.session.relinked", count=len(found)))
        after = self.media_status()
        return {"found": [{"id": m, "name": self.store.meta(m)["name"], "path": path}
                          for m, path in sorted(found.items())],
                "still_missing": after["missing"], "partial": after["partial"]}

    def check_replace_media(self, media_id: str, path: str) -> dict:
        """Locate / Relink media on a clip (owner, 2026-10-21), step one: bring
        ``path`` in and say what replacing ``media_id`` by it would mean, for the page
        to confirm.

        The same content (same SHA-256) is a plain relink of the moved file: no edit,
        and ``same_file`` is True. Other content (the recording edited elsewhere) is
        imported as new media, linked where it lies, so neither file is written or
        deleted (PLAN rule 17); nothing on the timeline changes until the page sends
        ``replace_clip_media``. Returns ``{same_file, new_media_id, name, old_frames,
        new_frames, same_length, clips}``."""
        if self.read_only:
            raise MediaError("error.media.read_only")
        bad = not isinstance(path, str) or not path.strip() or "\0" in path
        if bad or len(path) > 4096:
            raise MediaError("error.media.not_a_file", name=str(path or "")[:200])
        chosen = Path(path).expanduser()
        if not chosen.is_file():
            raise MediaError("error.media.not_a_file", name=str(chosen)[:200])
        with self.lock:
            project = self.history.state
        try:
            old = project.media_item(media_id)
        except KeyError:
            raise ops.EditError("error.edit.no_media", media_id=media_id) from None
        clips = sum(1 for t in project.tracks for c in t.clips if c.media == media_id)
        if file_sha256(chosen) == old.sha256:
            self.store.relink_one(media_id, chosen)
            new = old
        else:
            result = self.store.import_batch([str(chosen)], False)[0]
            self.last_import_report = [result]
            if not result.ok:
                raise result.error
            new = result.media
        return {"same_file": new.id == media_id, "new_media_id": new.id,
                "name": chosen.name, "old_frames": old.frames, "new_frames": new.frames,
                "same_length": old.frames == new.frames, "clips": clips}

    def stats(self) -> dict:
        """The session's statistics (WP70, ``project_stats``). Only the snapshot is
        taken under the lock; the history is read on its own connection and the
        counting, the words and the folder sizes run with the lock released."""
        return project_stats.gather(self.history, self.package.path, lock=self.lock,
                                    transcripts=self.transcripts)

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
            closed = offload.call("raw_silence_ranges", project, self.store)
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
                     track_naming: str = "file", start_frame: int = 0,
                     onto_track: str | None = None) -> Project:
        """``import_media_report`` without the report (it stays in
        ``last_import_report``). Raises if not one file could be imported."""
        return self.import_media_report(paths, copy=copy, track_per_file=track_per_file,
                                        interview=interview,
                                        interview_title=interview_title,
                                        mode=mode, order=order,
                                        track_naming=track_naming,
                                        start_frame=start_frame,
                                        onto_track=onto_track)[0]

    def import_media_report(self, paths: list[str], copy: bool = False,
                            track_per_file: bool = True, interview: bool | None = None,
                            interview_title: str | None = None, *,
                            mode: str | None = None, order: str = "given",
                            track_naming: str = "file", start_frame: int = 0,
                            onto_track: str | None = None,
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
        - ``onto_track``: put every file on this existing track, one after another from
          ``start_frame`` (no new track, no sync group). An unknown track is an error.

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
            if onto_track is not None:
                # Before any file is read: an unknown track must change nothing.
                ops._find_track(self.history.state, onto_track)
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

            if onto_track is not None:
                effective_mode = "sequential"
            elif mode is not None:
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
                if pl.new_track and onto_track is not None:
                    track_id = onto_track
                    track_ids_by_key[pl.track_key] = track_id
                elif pl.new_track:
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

            if onto_track is not None:
                # No layers: what the new clips land on is trimmed back, as for a move.
                p = ops._overwrite_under(self.history.state, p)
            refs = [m.time_ref_flicks for m in media]
            if effective_mode == "side_by_side" and len({m.id for m in media}) > 1:
                # Exact clocks when every file has one (or none does); mixed,
                # the files that have none were placed at 0, so the placement
                # on the timeline is what the group has to say.
                basis = "files" if len({r is None for r in refs}) == 1 else "timeline"
                p = ops.mark_in_sync(p, clip_ids, main=clip_ids[0], basis=basis)
            if onto_track is not None:
                # The target track decides: stereo on a music track stays stereo (no
                # "turn into mono?" question); on a speech track it is still offered.
                target = next(t for t in p.tracks if t.id == onto_track)
                stereo_in = any(pl.item.channels >= 2 for pl in placements)
                self.last_import_stereo = (
                    [{"id": target.id, "name": target.name}]
                    if stereo_in and target.kind == "speech" else [])
            else:
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
                                  "onto_track": onto_track,
                                  "interview": self.last_import_interview},
                                 material=root), report)

    def import_take(self, files: list[tuple[Path, int] | tuple[Path, int, int]], *,
                    track_id: str | None, track_name: str, clip_name: str,
                    take: str) -> tuple[Project, list[str]]:
        """A recorded take of one channel onto the timeline (WP12a): ``import_take_lanes``
        with a single lane."""
        return self.import_take_lanes([(files, track_id, track_name)],
                                      clip_name=clip_name, take=take)

    def import_take_lanes(
            self, lanes: list[tuple[list[tuple[Path, int] | tuple[Path, int, int]],
                                    str | None, str]], *, clip_name: str,
            take: str) -> tuple[Project, list[str]]:
        """A recorded take onto the timeline (WP12a, several channels WP12b), as ONE undo
        step.

        ``lanes``: one ``(files, track_id, track_name)`` per recorded channel. ``files``
        are the channel's WAVs in ``recordings/`` with the timeline frame each starts at
        (one per segment), and optionally how many frames to cut from the file's head
        (pre-roll that would fall before the timeline's start, WP12c; the file itself is
        never changed). They are linked in place, never copied. The clips go on
        ``track_id`` (what they land on is trimmed back, as for an import onto a track)
        or, when that is None or gone, on a new mono speech track named ``track_name``;
        a lane none of whose files could be imported makes no track. All the take's clips
        are one sync group: the channels share one clock, and the gaps between segments
        are real time. Returns the project and the new clips' ids. A file that cannot be
        imported is left out; when none can, nothing changes and its error is raised.
        """
        with self.lock:
            _check_writable(self)
            every = [f for files, _, _ in lanes for f in files]
            report = self.store.import_batch([str(f[0]) for f in every], copy=False)
            self.last_import_report = report
            ok = {id(f): r.media for r, f in zip(report, every, strict=True) if r.ok}
            if not ok:
                raise report[0].error
            before = p = self.history.state
            clip_ids = []
            lane_tracks: list[str] = []
            for files, wanted_track, track_name in lanes:
                placed = [(ok[id(f)], f[1], f[2] if len(f) > 2 else 0)
                          for f in files if id(f) in ok]
                placed = [(m, start, cut) for m, start, cut in placed if cut < m.frames]
                if not placed:
                    continue  # nothing of this channel to show: no empty track
                dest = wanted_track
                if dest is None or not any(tr.id == dest for tr in p.tracks):
                    dest = ops.new_id("t")
                    p = ops.add_track(p, dest, track_name, "speech")
                    p = ops.set_track(p, dest, mono=True)
                lane_tracks.append(dest)
                for media, start, cut in placed:
                    clip_id = ops.new_id("c")
                    p = ops.add_clip(p, dest, media.id, start=start, offset=cut,
                                     clip_id=clip_id)
                    p = ops.set_clip(p, clip_id, name=clip_name)
                    clip_ids.append(clip_id)
            p = ops._overwrite_under(before, p)
            if len(clip_ids) > 1:
                p = ops.mark_in_sync(p, clip_ids, main=clip_ids[0], basis="timeline")
            project = self._commit(t("history.record_take", name=clip_name), p,
                                   "import_take",
                                   {"take": take, "files": [str(f[0]) for f in every],
                                    "track_id": lane_tracks[0] if lane_tracks else None})
            return project, clip_ids

    def linked_files(self) -> set[Path]:
        """Where the project's linked media live (resolved): a take whose files are
        among them is already imported."""
        with self.lock:
            ids = [m.id for m in self.history.state.media]
        out = set()
        for media_id in ids:
            with contextlib.suppress(KeyError, OSError):
                where = self.store.meta(media_id).get("linked_path")
                if where:
                    out.add(Path(where).resolve())
        return out

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
        # A clipboard clip may use a recording that no track plays ("kari intro"):
        # those files come in too, so the clip can become a clipboard entry.
        clipboard_refs = {
            region.get("Ref", "")
            for _, clip in _nhsx_clipboard_clips(nhsx_session.tree.getroot())
            for region in nhsx_children(clip, "Region")
        }
        paths = {}
        missing = []
        for file_info in nhsx_session.files:
            found = nhsx_locate(nhsx_session, file_info)
            if (found and file_info.id in clipboard_refs
                    and Path(found).is_file()):
                available.add(str(Path(found).resolve()))
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

    def set_transcript(self, media_id: str, words: list[dict], label: str,
                       timing: str | None = None) -> Project:
        """A new transcript for one media: one step, undone with Undo. ``timing``
        (WP78): None keeps the media's timing marker, "" clears it, text sets it."""
        with self.lock:
            try:
                self.history.state.media_item(media_id)
            except KeyError:
                raise ops.EditError("error.edit.no_media", media_id=media_id) from None
            self.history.add_transcript(media_id, words, label=label, timing=timing)
            return self._changed()

    # -- transcription as a detached background job (WP79) -------------------

    #: How often the open project looks for finished background jobs.
    BACKGROUND_POLL_S = 1.0

    def transcribe(self, media_ids: list[str], model: str | None = None,
                   language: str | None = None, backend: str = "local",
                   force: bool = False) -> list[str]:
        """Start ONE background job for the chosen recordings (``local``:
        faster-whisper here; ``colab``: the WP78 tool). The job is a file in the
        project and a separate worker process (``kuulas.transcribe_worker``) that
        goes on when the window or the app is closed; the finished words are
        added by ``poll_background`` (here, or at the next open) as one undo step
        per media, and only where the transcript did not change meanwhile.
        Recordings used only on music tracks are refused (``error.transcribe.music_only``)
        unless ``force``: music is not transcribed nor uploaded to Colab by default.
        Returns the job id in a list."""
        ids = list(dict.fromkeys(media_ids))
        items, previous, names = [], {}, []
        with self.lock:
            self.history._check_writable()
            if not force:
                music = transcribable.music_only_ids(self.history.state)
                skipped = [i for i in ids if i in music]
                if skipped:
                    raise ops.EditError(
                        "error.transcribe.music_only",
                        names=", ".join(self.history.state.media_item(i).name
                                        for i in skipped if i))
            for media_id in ids:
                try:
                    item = self.history.state.media_item(media_id)
                except KeyError:
                    raise ops.EditError(
                        "error.edit.no_media", media_id=media_id) from None
                items.append({"id": media_id, "name": item.name,
                              "path": self.store.transcription_path(media_id)})
                previous[media_id] = self.history.material["transcripts"].get(media_id)
                names.append(item.name)
        colab = backend == "colab"
        job_id = bgjobs.create_job(
            self.package.path, backend="colab" if colab else "local", items=items,
            previous=previous, names=names, model=model if colab else (model or "small"),
            language=language, cpu_threads=max(1, os.cpu_count() or 1),
            settings=colab_module.resolve_settings(colab_module.load_settings())
            if colab else None, forced=force)
        self._launch_background(job_id)
        return [job_id]

    def _launch_background(self, job_id: str) -> None:
        try:
            bgjobs.launch_worker(bgjobs.job_file(self.package.path, job_id))
        except OSError as e:
            bgjobs.remove_files(self.package.path, job_id)
            raise bgjobs.BackgroundJobError("error.transcribe.cannot_start",
                                            error=str(e)) from e

    def background_jobs(self) -> list[dict]:
        """The project's transcription jobs as ``/api/jobs`` lists them: running,
        waiting, interrupted, failed (kept until dismissed), and those this run
        added to the project (shown as completed)."""
        folder = self.package.path
        self.poll_background()  # a result that is ready goes in before it is listed
        found = [d for job_id in bgjobs.job_ids(folder)
                 if (d := bgjobs.describe(folder, job_id)) is not None]
        if not self.read_only:
            for d in found:
                if d["state"] == "completed":  # the worker is done, the words not yet in
                    d.update(state="running", progress=0.99)
        shown = {d["id"] for d in found}
        return found + [d for job_id, d in self._finished_jobs.items()
                        if job_id not in shown]

    def is_background(self, job_id: str) -> bool:
        return job_id in self._finished_jobs \
            or bgjobs.job_file(self.package.path, job_id).is_file()

    def drain_notices(self) -> list[dict]:
        """The notices the background jobs made since the last call, once:
        ``[{kind: "ok" | "error", text, job}]``."""
        with self._notice_lock:
            notices, self._notices = self._notices, []
        return notices

    def _notify(self, kind: str, job_id: str, key: str, **params) -> None:
        with self._notice_lock:
            self._notices.append({"kind": kind, "job": job_id,
                                  "text": str(t(key, **params))})

    def poll_background(self) -> None:
        """Add every finished result to the project (once), with a notice. Not in a
        read-only project: a project another computer holds is not ours to change."""
        if self.read_only:
            return
        folder = self.package.path
        with self._ingest_lock:
            for job_id in bgjobs.job_ids(folder):
                try:
                    self._ingest(job_id)
                except OSError:
                    log.exception("could not take in background job %s", job_id)

    def _ingest(self, job_id: str) -> None:
        folder = self.package.path
        job = bgjobs.read_json(bgjobs.job_file(folder, job_id))
        status = bgjobs.read_json(bgjobs.status_file(folder, job_id)) or {}
        if job is None:
            return
        marker = bgjobs.read_json(bgjobs.marker_file(folder, job_id)) or {}
        done: dict[str, str] = dict(marker.get("media") or {})
        state = status.get("state")
        if state != "completed":
            info = bgjobs.describe(folder, job_id) or {}
            lost = info.get("state") in {"failed", "interrupted"}
            if lost and not marker.get("reported"):
                error = info.get("error") or {}
                self._notify("error", job_id, "notice.transcribe.failed",
                             names=", ".join(job.get("names") or []),
                             error=error.get("text", ""))
                bgjobs.write_json_atomic(bgjobs.marker_file(folder, job_id),
                                         {"media": {}, "reported": True})
            return
        mine = job.get("host") == package._hostname()
        names = {i["id"]: i["name"] for i in job.get("items", [])}
        new: dict[str, str] = {}
        for media_id in names:
            if media_id in done:
                continue
            outcome = self._ingest_one(job, job_id, media_id, mine)
            if outcome:
                new[media_id] = outcome
        if not new:
            return
        done.update(new)
        bgjobs.write_json_atomic(bgjobs.marker_file(folder, job_id),
                                 {"media": done, "reported": True})
        for what, key in (("added", "notice.transcribe.added"),
                          ("conflict", "notice.transcribe.conflict"),
                          ("invalid", "notice.transcribe.invalid"),
                          ("missing", "notice.transcribe.missing")):
            listed = [names[m] for m, o in new.items() if o == what]
            if listed:
                self._notify("ok" if what == "added" else "error", job_id, key,
                             names=", ".join(listed))
        if len(done) >= len(names) and all(o == "added" for o in done.values()):
            shown = bgjobs.describe(folder, job_id)
            bgjobs.remove_files(folder, job_id)
            if shown:
                self._finished_jobs[job_id] = {**shown, "state": "completed",
                                               "progress": 1.0, "error": None}
                while len(self._finished_jobs) > 20:
                    del self._finished_jobs[next(iter(self._finished_jobs))]

    def _ingest_one(self, job: dict, job_id: str, media_id: str, mine: bool) -> str:
        """Store one media's result. Returns ``added``, ``conflict`` (the transcript
        changed since the job started: the result file is kept), ``invalid`` (the
        file is unreadable), ``missing`` (the media is gone), or "" when the result
        has not arrived yet (another computer's, still syncing)."""
        path = bgjobs.result_file(self.package.path, job_id, media_id)
        if not path.is_file():
            return "missing" if mine else ""
        try:
            found = colab_module.read_words_json(path)
        except colab_module.ColabError:
            return "invalid"
        with self.lock:
            previous = (job.get("previous") or {}).get(media_id)
            if self.history.material["transcripts"].get(media_id) != previous:
                return "conflict"
            try:
                self.set_transcript(
                    media_id, found["words"],
                    t("history.transcript", media_id=media_id),
                    # A local engine made these words: no "ctc-v1" claim survives.
                    timing=found["timing"] if job.get("backend") == "colab" else "")
            except ops.EditError:
                return "missing"
        with contextlib.suppress(OSError):
            path.unlink()
        return "added"

    def cancel_background(self, job_id: str) -> None:
        """Cancel a running job; dismiss a failed or cancelled one; an interrupted
        one becomes cancelled. Refused for another computer's running job."""
        self._finished_jobs.pop(job_id, None)
        folder = self.package.path
        info = bgjobs.describe(folder, job_id)
        if info is None:
            return
        if info["state"] in {"failed", "cancelled"}:
            bgjobs.remove_files(folder, job_id)
        elif info["state"] != "completed":
            bgjobs.request_cancel(folder, job_id)

    def restart_background(self, job_id: str) -> None:
        """Run a failed, cancelled or interrupted job again from the start (a local
        run starts over; so does the Colab run), against the transcripts as they are
        now: restarting after "changed meanwhile" replaces the newer text."""
        folder = self.package.path
        info = bgjobs.describe(folder, job_id)
        job = bgjobs.read_json(bgjobs.job_file(folder, job_id))
        if info is None or job is None:
            raise bgjobs.BackgroundJobError("error.jobs.unknown", job_id=job_id)
        if info["foreign"]:
            raise bgjobs.BackgroundJobError("error.transcribe.foreign_host",
                                            host=info["host"])
        if info["state"] not in {"failed", "cancelled", "interrupted"}:
            raise bgjobs.BackgroundJobError("error.transcribe.not_restartable")
        with self.lock:
            self.history._check_writable()
            previous = {}
            music = (set() if job.get("forced")
                     else transcribable.music_only_ids(self.history.state))
            for item in job["items"]:
                if item["id"] in music:  # a track became music since the job was made
                    raise ops.EditError("error.transcribe.music_only", names=item["name"])
                try:
                    self.history.state.media_item(item["id"])
                except KeyError:
                    raise ops.EditError(
                        "error.edit.no_media", media_id=item["id"]) from None
                previous[item["id"]] = self.history.material["transcripts"].get(
                    item["id"])
        for path in bgjobs.jobs_dir(folder).glob(f"{job_id}.*"):
            if path != bgjobs.job_file(folder, job_id):
                path.unlink(missing_ok=True)
        package.write_json_atomic(bgjobs.job_file(folder, job_id),
                                  {**job, "previous": previous})
        package.write_json_atomic(bgjobs.status_file(folder, job_id), {
            "state": "queued", "progress": 0.0, "message": "", "indeterminate": True,
            "log": [], "pid": None, "host": job.get("host"), "finished": None})
        self._launch_background(job_id)

    def restart_interrupted(self) -> list[str]:
        """Restart every interrupted job of this computer; returns their ids."""
        restarted = []
        for info in self.background_jobs():
            if info["state"] == "interrupted" and not info["foreign"]:
                self.restart_background(info["id"])
                restarted.append(info["id"])
        return restarted

    def _watch_background(self) -> None:
        while not self._watch_stop.wait(self.BACKGROUND_POLL_S):
            try:
                self.poll_background()
            except Exception:  # the watcher must outlive one bad job file
                log.exception("background job poll failed")

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
    options = silence_options.parse(args)
    state = s.history.state
    ranges = offload.call("silence_ranges", state, s.store, options)
    new = analysis.apply_silence(state, ranges, args.get("track_ids"))
    return s._commit(t("history.auto_silence"), new, "auto_silence", args)


def _open_gates(s: Session, args: dict) -> Project:
    """Clear the gate of the given tracks (every track with a gate when none
    are named) as ONE undo step."""
    state = s.history.state
    ids = args.get("track_ids")
    ids = [tr.id for tr in state.tracks if tr.gate] if ids is None else list(ids)
    new = state
    for track_id in ids:
        new = ops.set_gate(new, track_id, ())
    return s._commit(t("history.open_gates"), new, "open_gates", args)


def _automix(s: Session, args: dict) -> Project:
    kwargs = {} if "depth_db" not in args else {"depth_db": float(args["depth_db"])}
    state = s.history.state
    lanes = offload.call("speech_lanes", state, s.store)
    new = analysis.automix(state, s.store, lanes=lanes, **kwargs)
    return s._commit(t("history.automix"), new, "automix", args)


def _duck_music(s: Session, args: dict) -> Project:
    measured = args.get("measured")
    style = args.get("style", measured.get("style", "gaps")
                     if isinstance(measured, dict) else "gaps")
    if measured is None:
        with s.lock:
            snapshot = s.history.state
        if style == "sidechain":
            measured = offload.call("duck_sidechain", snapshot, s.store)
            measured["style"] = style
        else:
            intervals = offload.call("anyone_talking_intervals", snapshot, s.store)
            measured = {"key": analysis.duck_key(snapshot), "intervals": intervals}
    valid_measurement = (isinstance(measured, dict) and
                         (isinstance(measured.get("curves"), dict) if style == "sidechain"
                          else isinstance(measured.get("intervals"), list)))
    if not valid_measurement:
        raise ops.EditError("error.edit.bad_arguments", name="duck_music",
                            detail="measured")
    with s.lock:
        state = s.history.state
        if measured.get("key") != analysis.duck_key(state):
            raise ops.EditError("error.music_duck.stale")
        if style == "sidechain":
            curves = measured.get("curves")
            if not isinstance(curves, dict):
                raise ops.EditError("error.edit.bad_arguments", name="duck_music",
                                    detail="curves")
            new = state
            for track in state.tracks:
                if track.kind == "music" and track.duck is not False:
                    new = ops.set_track_automation(new, track.id,
                                                   curves.get(track.id, ()))
        elif style == "gaps":
            new = analysis.duck_music(state, s.store, intervals=measured["intervals"])
        else:
            raise ops.EditError("error.edit.bad_arguments", name="duck_music",
                                detail="style")
        at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        new = music_duck.with_record(new, at)
        return s._commit(t("history.duck_music"), new, "duck_music", {})


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
    # The tracks given (the track scope of WP83), else all tracks, so the speakers
    # stay together.
    scope = s._range_scope(s.history.state, args.get("track_ids"))
    new = ops.ripple_delete(s.history.state, start, end, scope)
    quoted = " ".join(words[i]["w"] for i in chosen[:LABEL_WORDS])
    if len(chosen) > LABEL_WORDS:
        quoted += "…"
    # The range goes in the step so the statistics (WP70) can say how much time was cut.
    rest = {k: v for k, v in args.items() if k != "group_editing"}
    return s._commit(t("history.cut_words", text=quoted), new, "cut_words",
                     {**rest, "track_ids": scope, "start": start, "end": end})


def _sync_outcome(before: Project, ids: list[str], new: Project) -> dict:
    """What a resync of ``ids`` does (``new`` is ``ops.resync(before, ids)``), in one
    place so the command and its preview (``Session.sync_preview``) cannot disagree:
    how many moved, how many were free, and the message for the page."""
    clips = [before.clip(cid) for cid in ids]
    free = sum(1 for c in clips if c.free)
    grouped = [c for c in clips if before.sync_group(c.media) is not None]
    anchors = [c for c in grouped if c.media == before.sync_group(c.media).main]
    moved = sum(1 for cid in ids if new.clip(cid).start != before.clip(cid).start)
    anchor = _anchor_name(before, grouped[0]) if grouped else ""
    if moved:
        kind = "synced"
        message = t("toast.sync.synced", count=moved, anchor=anchor)
        if free:
            message += " · " + t("toast.sync.skipped_free", count=free)
    elif not grouped:
        kind, message = "ungrouped", t("toast.sync.ungrouped")
    elif anchors and len(anchors) == len(grouped) - free:
        kind, message = "anchor", t("toast.sync.anchor_only")
    else:
        kind, message = "nothing", t("toast.sync.nothing")
    return {"resynced": moved, "skipped": free, "kind": kind, "anchor": anchor,
            "message": message}


def _resync_clips(s: Session, ids: list[str]) -> Project:
    """Resync ``ids`` (free clips are skipped and counted) in one step; what
    happened, in words, is in ``s.last_resync`` for the page's message. Time
    only: a clip's track is not part of sync. A resync that moves nothing makes
    no history step."""
    before = s.history.state
    new = ops.resync(before, ids)
    s.last_resync = _sync_outcome(before, ids, new)
    moved = s.last_resync["resynced"]
    if not moved:
        return before
    skipped = s.last_resync["skipped"]
    return s._commit(t("history.resync", count=moved, skipped=skipped), new, "resync",
                     {"clip_ids": ids})


def _anchor_name(p: Project, clip) -> str:
    """The track the group's anchor sits on (its first piece), for messages."""
    group = p.sync_group(clip.media)
    for track in p.tracks:
        if any(c.media == group.main for c in track.clips):
            return track.name
    return ""


def _resync_ids(_p: Project, args: dict) -> list[str]:
    ids = list(args.get("clip_ids") or ())
    if not ids:
        raise ops.EditError("error.edit.no_selection")
    return ids


def _resync_from_ids(p: Project, args: dict) -> list[str]:
    ids = ops.clips_from(p, int(args["frame"]), args.get("track_id"))
    if not ids:
        raise ops.EditError("error.edit.no_selection")
    return ids


def _resync(s: Session, args: dict) -> Project:
    """R / Alt+Mod+R: resync the selected clips."""
    return _resync_clips(s, _resync_ids(s.history.state, args))


def _resync_from(s: Session, args: dict) -> Project:
    """Shift+Alt+Mod+R: resync every clip from ``frame`` on, on all tracks (the
    fix for an accidental one-track cut). Free clips are skipped and reported."""
    return _resync_clips(s, _resync_from_ids(s.history.state, args))


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


def _against(value: float | None) -> str:
    """Where the beds sit against the speech, in words: "10.0 dB under the speech"."""
    if value is None:
        return t("music_level.unknown")
    if value <= 0:
        return t("music_level.under", db=f"{-value:.1f}")
    return t("music_level.above", db=f"{value:.1f}")


def _set_music_level(s: Session, args: dict) -> Project:
    return s.set_music_level(args)


def _level_blocks(s: Session, args: dict) -> Project:
    return s.level_blocks(args)


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
                                  offset, args.get("track_ids"))
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
    made = s.package.backup()
    if made is None:
        # The timer only logs this; a backup asked for by hand is told it was not made.
        raise ops.EditError("error.package.backup_low_disk")
    s.last_backup = made
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
    "open_gates": _open_gates,
    "automix": _automix,
    "duck_music": _duck_music,
    "cut_words": _cut_words,
    "resync": _resync,
    "resync_from": _resync_from,
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
    "set_music_level": _set_music_level,
    "level_blocks": _level_blocks,
    "placeholder_take": _placeholder_take,
    "save_backup": _save_backup,
    "save_checkpoint": _save_checkpoint,
}

#: Commands that run without the session lock and take it only for their
#: snapshot and their commit: their work is slow and must not stall playback
#: or edits (ground rule 14).
LOCK_FREE_COMMANDS = frozenset({"candidates_detect", "match_loudness", "save_backup",
                                "set_music_level", "level_blocks", "duck_music"})
