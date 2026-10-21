"""The series commands on an open project (docs/design/SERIES.md).

Each project change is one ``History.commit`` (one undo step): saving links the
project and stores its copy of the settings; applying adds the series' tracks and sets
their values with the copy; detaching drops the link. The series file itself is not
project state (no undo), like the clipboard. Settings reach a project only through an
explicit command here, never on open.

Where the current values live today: the track layout in the project; Auto-Silence's
options in the user's view of the project (the UI sends them, ``auto_silence``); the
automixer's switches in the per-user ``automixer.json`` (``AUTOMIX_KEYS`` of them are
the series'). Apply writes the series' automixer values there (merged, nothing else
changes) and returns the Auto-Silence options for the UI to take.

Series music: the clips chosen as the series' standing material are clipboard entries
(references by SHA-256) in the series file, with the paths where each recording was
found. Placing them links a recording the episode lacks IN PLACE from one of those
paths after checking its hash (``clipboard_link``); nothing is copied, moved or
written to a recorded file (rule 17).
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import automix, clipboard_link, new_project, series_settings
from .clipboard import Entry, make_entry, same_content
from .clipboard import from_json as entry_from_json
from .clipboard_store import entry_dict
from .messages import t
from .ops import EditError
from .paste_apply import apply_paste
from .paste_plan import plan_paste
from .series_library import SeriesLibrary, SeriesLibraryError, entries_of, media_paths
from .silence_options import SilenceOptions

log = logging.getLogger("kuulas.series")


def _library() -> SeriesLibrary:
    return SeriesLibrary()


def _link(session) -> dict:
    link = session.state.series
    if not link or not link.get("id"):
        raise SeriesLibraryError("error.series.none")
    return link


def _commit(session, label: str, change, op: dict) -> None:
    with session.lock:
        new = change(session.history.state)
        session.history.commit(label, new, op=op)
        session._changed()


def current_settings(session, auto_silence: Any = None) -> dict:
    """The episode's values now: its layout, the Auto-Silence options the UI has
    (else the project's copy, else the defaults) and the automixer's stored values."""
    copy = (session.state.series or {}).get("settings") or {}
    if not isinstance(auto_silence, dict):
        auto_silence = copy.get("auto_silence") or SilenceOptions().as_dict()
    return series_settings.normalise_settings({
        "layout": series_settings.layout_of(session.state),
        "auto_silence": auto_silence,
        "automix": automix.load_settings().get("options") or {},
    })


def status(session, auto_silence: Any = None) -> dict:
    """What the Series dialog and the status line show: every series, this project's
    link (its copy included), whether the file was found, and the differing sections."""
    library = _library()
    link = session.state.series or None
    record = library.load(link["id"]) if link and link.get("id") else None
    differs: list[str] = []
    if record is not None:
        differs = series_settings.differences(current_settings(session, auto_silence),
                                              record.get("settings"))
    return {"list": [{"id": r["id"], "name": r["name"],
                      "music": len(entries_of(r))} for r in library.list()],
            "link": link, "found": record is not None, "differs": differs,
            "music": len(entries_of(record)),
            "folder": str(library.folder), "project": str(session.package.path)}


def save_defaults(session, *, name: Any = None, auto_silence: Any = None,
                  series_id: Any = None) -> dict:
    """"Save as series defaults…": the episode's values become the series'. The
    project's series (else ``series_id``, an existing one; else a new one named
    ``name``). A linked project whose file is gone gets it back under the same id."""
    library = _library()
    settings = current_settings(session, auto_silence)
    link = session.state.series or {}
    sid = link.get("id") or series_id
    if sid:
        record = library.load(sid)
        if record is None:
            record = library.create(name or link.get("name"), settings, series_id=sid)
        else:
            record = library.update(sid, settings=settings,
                                    name=name if name and str(name).strip() else None)
    else:
        record = library.create(name, settings)
    _commit(session, t("history.series_save"),
            lambda p: series_settings.link(p, record["id"], record["name"],
                                           record["settings"]),
            {"name": "series_save", "args": {"series_id": record["id"]}})
    return status(session, auto_silence)


def apply(session) -> dict:
    """"Apply series settings": tracks and buses (added or set, never removed), the
    automixer values, and the Auto-Silence options returned for the UI. One undo step.
    A missing series file is an error and changes nothing."""
    link = _link(session)
    record = _library().load(link["id"])
    if record is None:
        raise SeriesLibraryError("error.series.missing", series_id=link["id"])
    settings = series_settings.normalise_settings(record.get("settings"))
    if "automix" in settings:
        automix.merge_options(settings["automix"])  # before the commit: fails first

    def change(p):
        if "layout" in settings:
            p = series_settings.apply_layout(p, settings["layout"])
        return series_settings.link(p, record["id"], record["name"], settings)

    _commit(session, t("history.series_apply"), change,
            {"name": "series_apply", "args": {"series_id": record["id"]}})
    return {**status(session, settings.get("auto_silence")), "settings": settings}


def attach(session, series_id: Any) -> dict:
    """Choose a series for this project. Nothing is applied: the difference shows."""
    record = _library().load(series_id)
    if record is None:
        raise SeriesLibraryError("error.series.missing", series_id=str(series_id)[:80])
    _commit(session, t("history.series_attach"),
            lambda p: series_settings.link(p, record["id"], record["name"], {}),
            {"name": "series_attach", "args": {"series_id": record["id"]}})
    return status(session)


def detach(session) -> dict:
    """This project leaves its series; its tracks and settings stay. The file stays."""
    _link(session)
    _commit(session, t("history.series_detach"), series_settings.unlink,
            {"name": "series_detach", "args": {}})
    return status(session)


def rename(session, name: Any) -> dict:
    link = _link(session)
    record = _library().update(link["id"], name=name)
    _commit(session, t("history.series_rename"),
            lambda p: replace(p, series={**p.series, "name": record["name"]}),
            {"name": "series_rename", "args": {"name": record["name"]}})
    return status(session)


def new_episode(parent: Any, name: Any, series_id: Any) -> Path:
    """"New episode from series…": a new project at ``parent``/``name``.kuulas with
    the series' tracks and its copy of the settings. Returns its folder; opening a
    window on it is the caller's."""
    record = _library().load(series_id)
    if record is None:
        raise SeriesLibraryError("error.series.missing", series_id=str(series_id)[:80])
    target = new_project.project_path(parent, name)
    from .session import Session  # noqa: PLC0415 - the session pulls in audio libraries

    episode = Session(target)
    try:
        settings = series_settings.normalise_settings(record.get("settings"))

        def change(p):
            if "layout" in settings:
                p = series_settings.apply_layout(p, settings["layout"])
            return series_settings.link(p, record["id"], record["name"], settings)

        _commit(episode, t("history.series_new_episode"), change,
                {"name": "series_new_episode", "args": {"series_id": record["id"]}})
    finally:
        episode.close()
    return target


# -- series music -----------------------------------------------------------------------


def _record(session) -> tuple[dict, dict]:
    """``(link, record)`` of this project's series; an error when it has none or
    its file is not on this computer."""
    link = _link(session)
    record = _library().load(link["id"])
    if record is None:
        raise SeriesLibraryError("error.series.missing", series_id=link["id"])
    return link, record


def _parsed(raw_entries: list) -> list[Entry]:
    out = []
    for raw in raw_entries:
        try:
            out.append(entry_from_json(json.dumps(raw)))
        except (TypeError, KeyError, IndexError, AttributeError, ValueError):
            log.warning(t("log.series.bad_entry", series_id=""))
    return out


def _put(session, link: dict, record: dict, entry: Entry) -> int:
    """Put ``entry`` on the series shelf with where its recordings were seen; refuse
    one that is already there (same id, or the same references and length). Returns
    how many entries the shelf has now."""
    if any(same_content(entry, have) for have in _parsed(entries_of(record))):
        raise EditError("error.clipboard.already_on_shelf")
    media = dict(record.get("media") or {})
    for digest in sorted({ref.media_sha256 for ref in entry.refs}):
        known = media_paths(record, digest)
        seen = [p for p in session.store.seen_paths(digest) if p not in known]
        item = next((m for m in session.state.media if m.sha256 == digest), None)
        old = media.get(digest) if isinstance(media.get(digest), dict) else {}
        media[digest] = {**old, "name": item.name if item else old.get("name", ""),
                         "paths": [*known, *seen]}
    entries = [*entries_of(record), entry_dict(entry)]
    _library().update(link["id"], music={"entries": entries}, media=media)
    return len(entries)


def music_add(session, clip_ids: Any, name: Any = "") -> dict:
    """Add the chosen clips to the series music as one entry (references only)."""
    link, record = _record(session)
    ids = [str(c) for c in clip_ids] if isinstance(clip_ids, list) else []
    entry = session._describe(make_entry(
        session.state, ids, name=str(name or "")))
    count = _put(session, link, record, entry)
    return {**status(session), "music": count}


# -- the clipboard's series shelf (docs/design/CLIPBOARD-SHELVES.md) --------------------


def _no_entry(entry_id: str) -> Exception:
    from .session import NoSuchEntryError  # noqa: PLC0415 - the session pulls in audio

    return NoSuchEntryError("error.clipboard.no_entry", entry_id=str(entry_id)[:80])


def shelf_list(session) -> dict:
    """The series shelf for the Clipboard panel: ``{link: {id, name} | None, found,
    entries: [view...]}``, each entry in the same view as the project's clipboard (its
    missing-here count is against this project). No series is an empty shelf."""
    link = session.state.series or {}
    if not link.get("id"):
        return {"link": None, "found": False, "entries": []}
    record = _library().load(link["id"])
    project = session.state
    entries = _parsed(entries_of(record)) if record is not None else []
    return {"link": {"id": link["id"], "name": link.get("name", "")},
            "found": record is not None,
            "entries": [session._entry_view(e, project) for e in entries]}


def shelf_add(session, entry_id: Any) -> dict:
    """"Add to series shelf": a copy of one of this project's clipboard entries (same
    id) goes on the series shelf; the project's entry stays."""
    link, record = _record(session)
    entry = session.clipboard.load().get(str(entry_id))
    if entry is None:
        raise _no_entry(entry_id)
    _put(session, link, record, entry)
    return shelf_list(session)


def shelf_remove(session, entry_id: Any) -> dict:
    """Take an entry off the series shelf, and the paths of a recording no other entry
    there uses. Never a recording, never a project's clipboard."""
    link, record = _record(session)
    raw = entries_of(record)
    kept = [e for e in raw if e.get("id") != entry_id]
    if len(kept) == len(raw):
        raise _no_entry(entry_id)
    used = {ref.get("media_sha256") for e in kept for ref in e.get("refs") or []
            if isinstance(ref, dict)}
    media = {k: v for k, v in (record.get("media") or {}).items() if k in used}
    _library().update(link["id"], music={"entries": kept}, media=media)
    return shelf_list(session)


def shelf_adopt(session, entry_id: Any) -> dict:
    """"Copy to this project" from the series shelf: link the recordings the episode
    lacks from where the series saw them (hash-checked, in place), then adopt a copy
    into the project's clipboard. Returns its view; Paste here pastes it next."""
    _, record = _record(session)
    entry = next((e for e in _parsed(entries_of(record)) if e.id == entry_id), None)
    if entry is None:
        raise _no_entry(entry_id)
    have = {m.sha256 for m in session.state.media}
    for digest in sorted({r.media_sha256 for r in entry.refs} - have):
        _link_from_series(session, record, digest)
    return session.clipboard_adopt(entry_dict(entry), from_project=entry.source_project)


def _entries(session) -> tuple[dict, list]:
    _, record = _record(session)
    return record, _parsed(entries_of(record))


def _link_from_series(session, record: dict, digest: str) -> None:
    """Link a recording the episode lacks, in place, from where the series saw it
    (each path hash-checked first); else from the entry's source project."""
    for raw in media_paths(record, digest):
        path = Path(raw)
        if (path.is_file() and clipboard_link.has_digest(path, digest)
                and session.store.import_batch([path], copy=False)[0].ok):
            return


def music_to_clipboard(session) -> dict:
    """The series music into this project's clipboard, to paste anywhere."""
    _record, entries = _entries(session)
    for entry in entries:
        session.clipboard_adopt(entry_dict(entry), from_project=entry.source_project)
    return {"added": len(entries)}


def music_place(session) -> dict:
    """"Place series music on the timeline": every entry where it sat in the episode
    it came from, on the same-named tracks, over what is there (overwrite). One undo
    step. Missing recordings and entries whose tracks the episode lacks are reported."""
    record, entries = _entries(session)
    have = {m.sha256 for m in session.state.media}
    for entry in entries:
        for digest in sorted({r.media_sha256 for r in entry.refs} - have):
            _link_from_series(session, record, digest)
        session._link_missing_media(entry)
        have = {m.sha256 for m in session.state.media}
    placed, missing, skipped = 0, set(), []
    with session.lock:
        p = session.history.state
        for entry in entries:
            by_name = {track.name.strip().casefold(): track.id for track in p.tracks}
            slots = sorted({ref.track_slot for ref in entry.refs})
            names = list(entry.tracks)
            mapping = {}
            for slot in slots:
                wanted = names[slot].strip().casefold() if slot < len(names) else ""
                if wanted in by_name:
                    mapping[slot] = by_name[wanted]
            if len(mapping) < len(slots):
                skipped.append(entry.name)
                continue
            at = entry.span[0]
            plan = plan_paste(p, entry, at, "overwrite", mapping)
            missing.update(plan.missing)
            if not plan.placements:
                continue
            p = apply_paste(p, entry, plan, at, set(mapping.values()), "overwrite")
            placed += len(plan.placements)
        if placed:
            session.history.commit(t("history.series_music_place"), p,
                                   op={"name": "series_music_place",
                                       "args": {"series_id": record["id"]}})
            session._changed()
    return {"placed": placed, "missing": sorted(missing), "skipped": skipped}
