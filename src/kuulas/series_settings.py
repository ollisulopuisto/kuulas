"""What a series carries from one episode to the next (owner, 2026-10-21), pure.

A series is episodes recorded in the same place, so what was found for one episode
(the track layout, Auto-Silence's options, the automixer's de-bleed values) is the
right start for the next. The settings are three sections, each optional:

* ``layout``: the tracks (name, kind, speaker, bus by NAME, gain, pan, mono, loudness
  target, duck override, whether the kind follows the bus) and the buses (name, role,
  gain, pan, mute), in order;
* ``auto_silence``: ``SilenceOptions`` as a dict;
* ``automix``: the automixer switches that depend on the room (``AUTOMIX_KEYS``), with
  every value spelled out (the tool's default where the user set none).

Applying a layout adds what is missing and sets the stored values on the same-named
tracks and buses (names compared trimmed and case-blind); it never deletes a track or
a bus and never touches a clip. Everything here is tolerant of a damaged or hand-edited
file: a bad part is dropped or set to its default, never fatal. docs/design/SERIES.md.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import replace
from typing import Any

from . import ops
from .automix import OPTIONS, AutomixError, normalize_options
from .model import Project
from .silence_options import SilenceOptionError
from .silence_options import parse as parse_silence

#: The automixer switches a series carries: they depend on the room and the mics
#: (de-bleed, the rider and block levelling that follow it, the mic ducking against
#: bleed) and on the show's sound (where the music bed sits). The speaker balance cap
#: is the project's own (``hand_adjusted``); plug-ins are per machine.
AUTOMIX_KEYS = ("speech_debleed", "speech_rider", "block_level", "speech_mic_duck",
                "mic_duck_db", "bed_under_speech_db", "keep_music_level")
SECTIONS = ("layout", "auto_silence", "automix")
_KINDS = ("speech", "music")


def _name_key(name: str) -> str:
    return name.strip().casefold()


def _number(value: Any, default: float | None, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    if not math.isfinite(value):
        return default
    return min(high, max(low, float(value)))


# -- layout -------------------------------------------------------------------------


def layout_of(project: Project) -> dict:
    """The project's tracks and buses as a series layout (buses named, not by id)."""
    bus_names = {b.id: b.name for b in project.buses}
    return {
        "tracks": [{"name": t.name, "kind": t.kind, "speaker": t.speaker,
                    "bus": bus_names.get(t.bus) if t.bus else None,
                    "gain_db": t.gain_db, "pan": t.pan, "mono": t.mono,
                    "target_lufs": t.target_lufs, "duck": t.duck,
                    "follow_bus_role": t.follow_bus_role}
                   for t in project.tracks],
        "buses": [{"name": b.name, "kind": b.kind, "gain_db": b.gain_db, "pan": b.pan,
                   "mute": b.mute} for b in project.buses],
    }


def _bus(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    kind = raw.get("kind")
    return {"name": name, "kind": kind if kind in _KINDS else None,
            "gain_db": _number(raw.get("gain_db"), 0.0, -60.0, 24.0),
            "pan": _number(raw.get("pan"), 0.0, -1.0, 1.0),
            "mute": raw.get("mute") is True}


def _track(raw: Any, buses: set[str]) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    bus = raw.get("bus")
    bus = bus if isinstance(bus, str) and _name_key(bus) in buses else None
    speaker = raw.get("speaker")
    duck = raw.get("duck")
    kind = raw.get("kind")
    return {"name": name, "kind": kind if kind in _KINDS else "speech",
            "speaker": speaker if isinstance(speaker, str) else "",
            "bus": bus,
            "gain_db": _number(raw.get("gain_db"), 0.0, -60.0, 24.0),
            "pan": _number(raw.get("pan"), 0.0, -1.0, 1.0),
            "mono": raw.get("mono") is True,
            "target_lufs": _number(raw.get("target_lufs"), None, *ops.TARGET_LUFS_RANGE),
            "duck": duck if isinstance(duck, bool) else None,
            "follow_bus_role": raw.get("follow_bus_role") is True and bus is not None}


def normalise_layout(raw: Any) -> dict:
    """``raw`` as a clean layout: unreadable tracks and buses are dropped, duplicate
    names keep the first, bad values become defaults, a bus that is not listed is
    none."""
    raw = raw if isinstance(raw, dict) else {}
    buses: list[dict] = []
    seen: set[str] = set()
    for item in raw.get("buses") or ():
        bus = _bus(item)
        if bus is not None and _name_key(bus["name"]) not in seen:
            seen.add(_name_key(bus["name"]))
            buses.append(bus)
    tracks: list[dict] = []
    names: set[str] = set()
    for item in raw.get("tracks") or ():
        track = _track(item, seen)
        if track is not None and _name_key(track["name"]) not in names:
            names.add(_name_key(track["name"]))
            tracks.append(track)
    return {"tracks": tracks, "buses": buses}


def apply_layout(project: Project, raw_layout: Any) -> Project:
    """``project`` with the layout's buses and tracks: same-named ones get the stored
    values, missing ones are added at the end. Nothing is removed; clips are untouched."""
    layout = normalise_layout(raw_layout)
    p = project
    bus_ids: dict[str, str] = {}
    for bus in layout["buses"]:
        found = next((b for b in p.buses if _name_key(b.name) == _name_key(bus["name"])),
                     None)
        if found is None:
            bus_id = ops.new_id("b")
            p = ops.add_bus(p, bus_id, bus["name"])
        else:
            bus_id = found.id
        p = ops.set_bus(p, bus_id, kind=bus["kind"], gain_db=bus["gain_db"],
                        pan=bus["pan"], mute=bus["mute"])
        bus_ids[_name_key(bus["name"])] = bus_id
    for track in layout["tracks"]:
        found = next((t for t in p.tracks
                      if _name_key(t.name) == _name_key(track["name"])), None)
        if found is None:
            track_id = ops.new_id("t")
            p = ops.add_track(p, track_id, track["name"], kind=track["kind"])
        else:
            track_id = found.id
        bus_id = bus_ids.get(_name_key(track["bus"])) if track["bus"] else None
        fields: dict[str, Any] = {
            "speaker": track["speaker"], "gain_db": track["gain_db"], "pan": track["pan"],
            "mono": track["mono"], "target_lufs": track["target_lufs"],
            "duck": track["duck"], "bus": bus_id}
        if track["follow_bus_role"] and bus_id is not None and p.bus(bus_id).kind:
            fields["follow_bus_role"] = True
        else:
            fields["kind"] = track["kind"]
        p = ops.set_track(p, track_id, **fields)
    return p


# -- the other sections --------------------------------------------------------------


def automix_values(stored: Any) -> dict:
    """The series keys' values in the automixer's stored options (which hold only
    what differs from the tool's defaults), the defaults filled in."""
    stored = stored if isinstance(stored, dict) else {}
    values: dict[str, Any] = {}
    for key in AUTOMIX_KEYS:
        value = stored.get(key, OPTIONS[key]["default"])
        try:
            checked = normalize_options({key: value}, resolve=False)
        except AutomixError:
            checked = {}
        values[key] = checked.get(key, OPTIONS[key]["default"])
    return values


def _auto_silence(raw: Any) -> dict:
    """Option by option, so one bad value costs only itself."""
    raw = raw if isinstance(raw, dict) else {}
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        with contextlib.suppress(SilenceOptionError):
            clean.update({k: v for k, v in parse_silence({key: value}).as_dict().items()
                          if k == key})
    return parse_silence(clean).as_dict()


def normalise_settings(raw: Any) -> dict:
    """The sections ``raw`` holds, each cleaned; unknown keys are dropped."""
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, Any] = {}
    if "layout" in raw:
        clean["layout"] = normalise_layout(raw["layout"])
    if "auto_silence" in raw:
        clean["auto_silence"] = _auto_silence(raw["auto_silence"])
    if "automix" in raw:
        clean["automix"] = automix_values(raw["automix"])
    return clean


def _layout_differs(current: Any, series: Any) -> bool:
    """Every series track and bus must be in the episode with the same values;
    extra tracks in the episode (a guest) are not a difference."""
    now, want = normalise_layout(current), normalise_layout(series)
    for kind in ("tracks", "buses"):
        have = {_name_key(item["name"]): item for item in now[kind]}
        for item in want[kind]:
            other = have.get(_name_key(item["name"]))
            if other is None:
                return True
            if {k: v for k, v in other.items() if k != "name"} != {
                    k: v for k, v in item.items() if k != "name"}:
                return True
    return False


def differences(current: Any, series: Any) -> list[str]:
    """The sections (in ``SECTIONS`` order) where the episode's values differ from the
    series'. A section the series does not hold is no difference."""
    now, want = normalise_settings(current), normalise_settings(series)
    out = []
    for section in SECTIONS:
        if section not in want:
            continue
        if section == "layout":
            if _layout_differs(now.get("layout"), want["layout"]):
                out.append(section)
        elif now.get(section) != want[section]:
            out.append(section)
    return out


# -- the project's link -------------------------------------------------------------


def link(project: Project, series_id: str, name: str, settings: dict) -> Project:
    """``project`` pointing at the series, with its own copy of ``settings``."""
    return replace(project, series={"id": series_id, "name": name,
                                    "settings": normalise_settings(settings)})


def unlink(project: Project) -> Project:
    """``project`` belonging to no series (its tracks and settings stay as they are)."""
    return replace(project, series={})
