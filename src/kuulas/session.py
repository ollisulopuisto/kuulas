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
from nhsx.read import descendants as nhsx_descendants
from nhsx.read import time_to_seconds as nhsx_time_to_seconds

from . import analysis, ops, package, transcribe, transcript
from . import db as dbm
from . import export as export_module
from . import music_report as music_report_module
from .clock import FLICKS, flicks_to_frames
from .history import History, UndoInfo
from .jobs import Jobs
from .media import ImportResult, MediaError, MediaStore
from .messages import KuulasError, t
from .model import Project, SyncGroup
from .people import Interview, Passage, Person

log = logging.getLogger("kuulas.session")


class NhsxImportError(KuulasError, ValueError):
    """A Hindenburg session could not be parsed or mapped safely."""


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

    def __init__(self, folder: str | Path, rate: int = 48000):
        folder = Path(folder)
        self.lock = threading.RLock()
        if (folder / "manifest.json").exists() or (folder / "project.sqlite").exists():
            self.package = package.open_package(folder)
            is_new = False
        else:
            self.package = package.create(folder, rate)
            is_new = True
        self.package.start()
        self.jobs = Jobs()
        self.history: History = self.package.history
        self.store: MediaStore = self.package.store
        self._subscribers: list[Callable[[Project], None]] = []
        #: What became of each file in the latest import (WP34), for the UI
        #: to show: the failures and why, and the warnings of those that came in.
        self.last_import_report: list[ImportResult] = []
        #: The interview the latest import made (WP41), or None.
        self.last_import_interview: str | None = None
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
        transcript. See ``COMMANDS``."""
        with self.lock:
            if args is None:
                args = {}
            try:
                run = COMMANDS[name]
            except KeyError:
                raise ops.EditError("error.edit.unknown", name=name) from None
            return run(self, args)

    def duck_music(self) -> Project:
        return self.command("duck_music")

    def _commit(self, label: str, new: Project, name: str, args: dict,
                material: dict | None = None) -> Project:
        self.history.commit(label, new, op={"name": name, "args": args},
                            material=material)
        return self._changed()

    def _material_step(self, label: str, root: dict, name: str, args: dict) -> None:
        """One undo step that changes only material (people, interviews, maps)."""
        self.history.set_material(label, root, op={"name": name, "args": args})
        self._changed()

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

    def last_export_settings(self, kind: str) -> dict | None:
        """Return the project's remembered settings for an export kind."""
        return export_module.last_settings(self, kind)

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

    # -- import ------------------------------------------------------------

    def import_media(self, paths: list[str], copy: bool = False,
                     track_per_file: bool = True, interview: bool | None = None,
                     interview_title: str | None = None) -> Project:
        """``import_media_report`` without the report (it stays in
        ``last_import_report``). Raises if not one file could be imported."""
        return self.import_media_report(paths, copy, track_per_file, interview,
                                        interview_title)[0]

    def import_media_report(self, paths: list[str], copy: bool = False,
                            track_per_file: bool = True, interview: bool | None = None,
                            interview_title: str | None = None,
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
            made_group = bool(p.sync_groups) and track_per_file and len(
                {m.id for m in media}) > 1
            root = self._with_import_interview(
                p, media, interview, interview_title, made_group)
            # Only what came in is recorded: replaying the step must not
            # depend on files that failed.
            return (self._commit(label, p, "import_media",
                                 {"paths": [x for x, _ in ok], "copy": copy,
                                  "track_per_file": track_per_file,
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
                    kind = "music" if media.channels >= 2 else "speech"
                    p = ops.add_track(p, track_id, source_track.name or "Track", kind)
                    p = ops.set_track(p, track_id, gain_db=track_gain, pan=track_pan,
                                      mute=track_muted)
                    p = ops.set_track_extra(p, track_id, "nhsx", {
                        "source_xml": _element_xml(track_elem)})
                clip_id = ops.new_id("c")
                p = ops.add_clip(p, track_id, media.id, start=start, offset=offset,
                                 length=length, clip_id=clip_id)
                elem = region.elem
                clip_gain = elem.get("ClipGain")
                region_gain = (_db_value(clip_gain) if clip_gain is not None
                               else _db_value(elem.get("Gain")))
                region_pan = _db_value(elem.get("Pan"))
                fade_in = round(_time_value(elem.get("FadeIn")) * self.history.rate)
                fade_out = round(_time_value(elem.get("FadeOut")) * self.history.rate)
                p = ops.set_clip(p, clip_id, gain_db=region_gain,
                                 pan=max(-1.0, min(1.0, region_pan)),
                                 fade_in=fade_in, fade_out=fade_out,
                                 muted=_truth(elem.get("Muted")))
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

        if p == self.history.state and root == self.history.material:
            return p
        p = replace(p, extra={**p.extra, "nhsx": {"source_xml": source_xml}})
        self.last_import_interview = None
        return self._commit(t("history.nhsx_import", name=source.name), p,
                            "import_nhsx", {"path": str(source)}, material=root)

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


#: Name -> function(session, args) -> Project. The session lock is held.
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
}
