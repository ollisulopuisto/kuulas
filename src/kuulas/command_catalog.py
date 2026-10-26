"""The command catalogue (WP53): every edit and every session command, with its arguments
and a one-line summary, so a program or an LLM can find what kuulas can do without knowing
it in advance. ``GET /api/commands`` serves it.

Edits (``ops.OPS``) are described from their signatures and docstrings, so they cannot
drift. Session commands and the clipboard edits take a plain dict, so they are described
here by hand; ``tests/test_command_catalog.py`` fails when one is missing from the table.

The call is ``POST /api/edit {"op": name, "args": {...}}`` for an edit and
``POST /api/command {"name": name, "args": {...}}`` for a session command. ``undo_step``
says whether the command makes one step in the history (so one undo takes it back); the
others change data kept with the project (people, interviews, candidates, saved versions)
or only read and copy files.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

from . import ops
from .session import CLIPBOARD_EDITS, COMMANDS

CALLS = {
    "/api/edit": 'POST {"op": name, "args": {...}, "label": optional}: an edit',
    "/api/command": 'POST {"name": name, "args": {...}}: a session command',
}


def _arg(name: str, type_: str | None, *, required: bool = False, default: Any = None,
         note: str = "", variadic: bool = False) -> dict:
    entry: dict[str, Any] = {"name": name, "type": type_, "required": required}
    if not required:
        entry["default"] = default
    if note:
        entry["note"] = note
    if variadic:
        entry["variadic"] = True
    return entry


def _plain(value: Any) -> Any:
    """A default as JSON, or its repr when it is not plain data."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value


def _signature_args(function, skip: tuple[str, ...]) -> list[dict]:
    args = []
    for name, param in inspect.signature(function).parameters.items():
        if name in skip:
            continue
        empty = param.annotation is inspect.Parameter.empty
        type_ = None if empty else str(param.annotation)
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            args.append(_arg(name, "keyword arguments", note="any field of the item",
                             variadic=True))
        elif param.default is inspect.Parameter.empty:
            args.append(_arg(name, type_, required=True))
        else:
            args.append(_arg(name, type_, default=_plain(param.default)))
    return args


def _first_line(text: str | None) -> str:
    return " ".join((text or "").strip().split("\n", 1)[0].split())


IDS = "list[str]"
# Session commands: name -> (summary, undo_step, arguments). ``undo_step`` was read from
# the code (does the command, or a Session method it calls, commit to the history).
SESSION: dict[str, tuple[str, bool, list[dict]]] = {
    "auto_silence": (
        "Close each speech microphone where its owner is not talking, as one merged gate "
        "per track.", True, [
            _arg("track_ids", IDS, note="default: every speech track"),
            _arg("method", "str", note="threshold or compensated"),
            _arg("margin_db", "number", note="3 to 20"),
            _arg("dominance_db", "number", note="0 to 30"),
            _arg("min_open_s", "number", note="0 to 5"),
            _arg("min_closed_s", "number", note="0 to 5"),
            _arg("open_before_s", "number", note="0 to 3"),
            _arg("open_after_s", "number", note="0 to 5"),
        ]),
    "open_gates": (
        "Clear Auto-Silence from the given tracks.", True,
        [_arg("track_ids", IDS, note="default: every track that has any")]),
    "automix": (
        "Duck the music under speech and set the speech levels, as the automixer does.",
        True,
        [_arg("depth_db", "number", note="how far the music is ducked")]),
    "duck_music": (
        "Duck the music wherever anyone talks.", True, [
            _arg("style", "str", default="gaps", note="gaps or sidechain"),
            _arg("measured", "object", note="a finished measurement job's result"),
        ]),
    "cut_words": (
        "Delete words from the audio: their stretch is ripple-deleted on the tracks.",
        True, [
            _arg("indices", "list[int]", required=True, note="transcript word indices"),
            _arg("track_ids", IDS, note="default: all tracks"),
        ]),
    "put_back": (
        "Put a removed stretch back as a ripple insert; only clips are added.", True, [
            _arg("media", "str", required=True),
            _arg("start", "int", required=True, note="frame in the media"),
            _arg("end", "int", required=True, note="frame in the media"),
            _arg("at", "int", note="the frame to put it at, when the place is unclear"),
            _arg("track_ids", IDS),
        ]),
    "resync": (
        "Resync the given clips to their sync anchor.", True,
        [_arg("clip_ids", IDS, required=True)]),
    "resync_from": (
        "Resync every clip from a frame on, on all tracks (or one).", True, [
            _arg("frame", "int", required=True),
            _arg("track_id", "str"),
        ]),
    "relink": (
        "Find moved media again by content. Not an edit.", False,
        [_arg("folder", "str", note="where to look")]),
    "consolidate": ("Copy linked media into the project. Not an edit.", False, []),
    "create_person": (
        "Add a person (a speaker or guest) to the project.", False, [
            _arg("name", "str", default=""), _arg("role", "str", default=""),
            _arg("aliases", "list[str]", default=[]), _arg("notes", "str", default=""),
        ]),
    "edit_person": (
        "Change a person's name, role, aliases or notes.", False, [
            _arg("id", "str", required=True),
            _arg("fields", "keyword arguments", note="name, role, aliases, notes",
                 variadic=True),
        ]),
    "delete_person": ("Delete a person.", False, [_arg("id", "str", required=True)]),
    "create_interview": (
        "Add an interview (a titled group of media) to the project.", False, [
            _arg("title", "str", default=""),
            _arg("fields", "keyword arguments", note="other fields", variadic=True),
        ]),
    "edit_interview": (
        "Change an interview's fields.", False, [
            _arg("id", "str", required=True),
            _arg("fields", "keyword arguments", variadic=True),
        ]),
    "delete_interview": (
        "Delete an interview.", False, [_arg("id", "str", required=True)]),
    "set_media_person": (
        "Say which person a media file is of.", False, [
            _arg("media", "str", required=True),
            _arg("person", "str", note="a person id; none clears it"),
        ]),
    "set_music_info": (
        "Set the title, artist and other info of a music file.", False, [
            _arg("media", "str", required=True, note="also accepted as media_id or id"),
            _arg("fields", "object", note="the info fields; other keys count as fields"),
        ]),
    "map_speakers": (
        "Map the speaker names a transcript uses to people.", False, [
            _arg("media", "str", required=True),
            _arg("map", "object", default={}),
        ]),
    "import_nhsx": (
        "Import a Hindenburg session (.nhsx) into the project.", True,
        [_arg("path", "str", required=True)]),
    "rebuild_media": (
        "Rebuild a media file's derived data (peaks and the like).", False, [
            _arg("media", "str", required=True, note="also accepted as id"),
            _arg("path", "str", note="a file to rebuild it from"),
        ]),
    "candidates_detect": (
        "Look for cut candidates (fillers, repeats and the like) in the transcript.",
        False, [
            _arg("lang", "str"), _arg("levels", "bool"),
        ]),
    "candidate_set_state": (
        "Set a cut candidate's state (for example kept or rejected).", False, [
            _arg("id", "str", required=True), _arg("state", "str", default=""),
        ]),
    "candidate_apply": (
        "Apply a cut candidate to the edit.", True, [
            _arg("id", "str", required=True),
            _arg("mode", "str", default="soft"),
            _arg("tracks", IDS),
        ]),
    "candidate_mark": (
        "Mark a stretch as a cut candidate by hand.", False, [
            _arg("start", "int", required=True), _arg("end", "int", required=True),
            _arg("track_id", "str"),
        ]),
    "match_loudness": (
        "Match the loudness of the given clips to a target.", True, [
            _arg("clip_ids", IDS, default=[]),
            _arg("target_lufs", "number"),
        ]),
    "set_music_level": (
        "Set the music level against the speech, on each music track's gain.", True, [
            _arg("offset_db", "number", note="the beds' loudest moment vs the speech"),
            _arg("mode", "str", default="common"),
            _arg("measured", "object", note="a finished measurement job's result"),
        ]),
    "level_blocks": (
        "Split each speaker's clips in the pauses and level the blocks.", True, [
            _arg("skip", IDS, default=[], note="block ids to leave alone"),
            _arg("markers", "bool", note="put a marker at each loud spot"),
            _arg("measured", "object", note="a finished measurement job's result"),
        ]),
    "placeholder_take": (
        "Import one file and make it the take of a narration placeholder.", True, [
            _arg("placeholder_id", "str", required=True),
            _arg("path", "str", required=True),
            _arg("offset", "int", default=0),
            _arg("copy", "bool", default=False),
            _arg("track_ids", IDS),
        ]),
    "save_backup": ("Make a backup copy of the project now.", False, []),
    "save_checkpoint": (
        "Mark the current step as a saved version. Changes no edit state.", False, [
            _arg("name", "str", note="default: the standard name"),
            _arg("rename", "bool", note="rename the existing version instead"),
        ]),
    "rename_checkpoint": (
        "Rename a saved version. Changes no edit state.", False, [
            _arg("node", "str", required=True), _arg("name", "str", required=True),
        ]),
}

CLIPBOARD: dict[str, tuple[str, list[dict]]] = {
    "clipboard_cut": (
        "Cut a stretch: ripple-delete [start, end) and keep it as a clipboard entry.", [
            _arg("start", "int", required=True), _arg("end", "int", required=True),
            _arg("track_ids", IDS), _arg("name", "str", default=""),
        ]),
    "clipboard_lift_cut": (
        "Lift-cut a stretch: copy [start, end) to the clipboard and delete it, "
        "leaving a gap.",
        [
            _arg("start", "int", required=True), _arg("end", "int", required=True),
            _arg("track_ids", IDS), _arg("name", "str", default=""),
        ]),
    "clipboard_paste": (
        "Paste a clipboard entry at a frame.", [
            _arg("entry_id", "str", required=True),
            _arg("at", "int", required=True),
            _arg("mode", "str", default="insert"),
            _arg("target_tracks", IDS),
            _arg("out", "int"),
        ]),
}


def catalog() -> list[dict]:
    """Every command, edits first: { name, via, summary, undo_step, args }."""
    entries = []
    for name, function in ops.OPS.items():
        entries.append({
            "name": name, "via": "/api/edit", "undo_step": True,
            "summary": _first_line(inspect.getdoc(function)),
            "args": _signature_args(function, skip=("p",)),
        })
    for name in CLIPBOARD_EDITS:
        summary, args = CLIPBOARD[name]
        entries.append({"name": name, "via": "/api/edit", "undo_step": True,
                        "summary": summary, "args": args})
    for name in COMMANDS:
        summary, undo_step, args = SESSION[name]
        entries.append({"name": name, "via": "/api/command", "undo_step": undo_step,
                        "summary": summary, "args": args})
    return entries

