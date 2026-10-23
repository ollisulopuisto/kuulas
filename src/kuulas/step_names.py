"""Readable History step names, made when the list is read, not when a step is stored.

A step keeps the op that made it (``{"name", "args"}``). Its name in the History panel is
built from that op, the arguments and the *current* state (track names), in the language
of the request: ``Track settings: Olli · gain -3.0 dB``, ``Split: Anna at 12:34.5``. The
label stored with the step is only the fallback for an op with no describer here; old
steps whose label froze a raw op id (``set_track``) read well too.

``describe`` answers ``{"name", "base", "detail", "run"}``: ``base`` and ``detail``
let the panel show a run of steps on one object as one row (``Olli x4 · gain -3 -> -9``);
``run`` is the key such a run shares (op and object), ``None`` when steps never merge.
``tests/test_step_names.py`` keeps every op in ``ops.OPS`` covered.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from typing import Any

from .messages import language, t
from .model import Project

Args = dict[str, Any]
#: Numbers in names use the real minus sign, as the rest of the UI does.
MINUS = "\u2212"


class _Context:
    """Looks things up in the current state; a missing one falls back to a word."""

    def __init__(self, state: Project):
        self.state = state
        self.rate = state.rate or 48000

    def track(self, track_id: Any) -> str:
        for track in self.state.tracks:
            if track.id == track_id:
                return track.name or t("history.op.a_track")
        return t("history.op.a_track")

    def clip_track(self, clip_id: Any) -> str | None:
        for track in self.state.tracks:
            if any(c.id == clip_id for c in track.clips):
                return track.name or t("history.op.a_track")
        return None

    def where(self, clip_ids: Any) -> str:
        """The one track the clips are on, else how many tracks; deleted: a track."""
        ids = clip_ids if isinstance(clip_ids, list | tuple) else [clip_ids]
        names = {n for n in (self.clip_track(c) for c in ids) if n is not None}
        if len(names) == 1:
            return names.pop()
        if names:
            return t("history.op.tracks", count=len(names))
        return t("history.op.a_track")

    def bus(self, bus_id: Any) -> str:
        for bus in self.state.buses:
            if bus.id == bus_id:
                return bus.name or t("history.op.a_bus")
        return t("history.op.a_bus")

    def marker(self, marker_id: Any) -> str:
        for m in self.state.markers:
            if m.id == marker_id:
                return m.name or t("history.op.a_marker")
        return t("history.op.a_marker")

    def at(self, frames: Any) -> str:
        """A timeline position as m:ss.s (h:mm:ss.s past an hour), decimal comma in fi."""
        try:
            tenths = round(int(frames) * 10 / self.rate)
        except (TypeError, ValueError):
            return "?"
        sign = MINUS if tenths < 0 else ""
        tenths = abs(tenths)
        seconds, tenth = divmod(tenths, 10)
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        mark = "," if language() == "fi" else "."
        head = f"{hours}:{minutes:02d}" if hours else f"{minutes}"
        return f"{sign}{head}:{sec:02d}{mark}{tenth}"

    def length(self, frames: Any) -> str:
        try:
            return t("history.op.seconds", value=_decimal(abs(int(frames)) / self.rate))
        except (TypeError, ValueError):
            return "?"

    def span(self, args: Args) -> str:
        try:
            return self.length(int(args["end"]) - int(args["start"]))
        except (KeyError, TypeError, ValueError):
            return "?"


def _decimal(value: float, signed: bool = False) -> str:
    text = f"{value:+.1f}" if signed else f"{value:.1f}"
    text = text.replace("-", MINUS)
    return text.replace(".", ",") if language() == "fi" else text


def _db(value: Any, signed: bool = False) -> str:
    try:
        return t("history.op.db", value=_decimal(float(value), signed))
    except (TypeError, ValueError):
        return "?"


def _count(args: Args, key: str = "clip_ids") -> int:
    value = args.get(key)
    return len(value) if isinstance(value, list | tuple) else 1


#: Settings a step changed, as short words after the name ("gain -3.0 dB · muted").
def _fields(args: Args) -> str:
    parts = []
    if "gain_db" in args:
        parts.append(t("history.op.field.gain", db=_db(args["gain_db"])))
    if "pan" in args:
        with suppress(TypeError, ValueError):
            pan = _decimal(float(args["pan"]), signed=True)
            parts.append(t("history.op.field.pan", value=pan))
    parts.extend(t("history.op.field.muted" if args[key] else "history.op.field.unmuted")
                 for key in ("mute", "muted") if key in args)
    if "solo" in args:
        parts.append(t("history.op.field.solo_on" if args["solo"] else
                       "history.op.field.solo_off"))
    if args.get("name"):
        parts.append(t("history.op.field.name", name=str(args["name"])))
    return " · ".join(parts)


def _short(text: Any, limit: int = 40) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Each describer answers (message values, detail, run object). The message is
# "history.op.<op name>"; values it does not name are ignored.
Described = tuple[dict[str, Any], str, str | None]
Describer = Callable[[Args, _Context], Described]


def _on_track(args: Args, c: _Context) -> Described:
    return {"track": c.track(args.get("track_id"))}, "", args.get("track_id")


def _track_settings(args: Args, c: _Context) -> Described:
    return {"track": c.track(args.get("track_id"))}, _fields(args), args.get("track_id")


def _on_clip(args: Args, c: _Context) -> Described:
    clip = args.get("clip_id")
    return ({"track": c.clip_track(clip) or t("history.op.a_track"),
             "at": c.at(args.get("at", args.get("start", args.get("frame"))))}, "", clip)


def _clip_settings(args: Args, c: _Context) -> Described:
    values, _, clip = _on_clip(args, c)
    return values, _fields(args), clip


def _on_clips(args: Args, c: _Context) -> Described:
    ids = args.get("clip_ids") or []
    key = ",".join(sorted(map(str, ids))) if isinstance(ids, list | tuple) else str(ids)
    return ({"count": _count(args), "where": c.where(ids), "at": c.at(args.get("at")),
             "delta": c.length(args.get("delta", 0))}, "", key or None)


def _clips_settings(args: Args, c: _Context) -> Described:
    values, _, key = _on_clips(args, c)
    return values, _fields({k: v for k, v in args.items() if k != "clip_ids"}), key


def _clip_gain(args: Args, c: _Context) -> Described:
    values, _, key = _on_clips(args, c)
    return values, _db(args.get("delta_db", 0), signed=True), key


def _range(args: Args, c: _Context) -> Described:
    return {"length": c.span(args), "at": c.at(args.get("start"))}, "", None


def _bus(args: Args, c: _Context) -> Described:
    return {"bus": c.bus(args.get("bus_id"))}, _fields(args), args.get("bus_id")


def _named(args: Args, _c: _Context) -> Described:
    return {"name": _short(args.get("name")) or "?"}, "", None


def _marker(args: Args, c: _Context) -> Described:
    marker = args.get("marker_id")
    return ({"marker": c.marker(marker), "name": _short(args.get("name")) or "?",
             "at": c.at(args.get("start", args.get("end")))}, "", marker)


def _add_marker(args: Args, c: _Context) -> Described:
    return ({"name": _short(args.get("name")) or "?", "at": c.at(args.get("start"))},
            "", None)


def _placeholder(args: Args, c: _Context) -> Described:
    return ({"text": _short(args.get("text")) or "?", "at": c.at(args.get("start")),
             "length": c.length(args.get("length", 0))}, "", args.get("placeholder_id"))


def _plain(_args: Args, _c: _Context) -> Described:
    return {}, "", None


def _master(args: Args, _c: _Context) -> Described:
    return {}, _db(args.get("gain_db", 0)), "master"


def _ungated(args: Args, c: _Context) -> Described:
    values, detail, key = _on_clips(args, c)
    on = args.get("value", True)
    state = t("history.op.field.on" if on else "history.op.field.off")
    return {**values, "state": state}, detail, key


DESCRIBERS: dict[str, Describer] = {
    "add_track": _named,
    "delete_track": _on_track,
    "delete_empty_tracks": _plain,
    "set_track": _track_settings,
    "solo": _on_track,
    "move_track": _on_track,
    "set_track_automation": _on_track,
    "add_bus": _named,
    "set_bus": _bus,
    "delete_bus": _bus,
    "set_master": _master,
    "reset_gains": _plain,
    "add_clip": lambda a, c: ({"track": c.track(a.get("track_id")),
                               "at": c.at(a.get("start", 0))}, "", None),
    "delete_clip": _on_clip,
    "move_clip": _on_clip,
    "trim_clip": _on_clip,
    "split_clip": _on_clip,
    "set_clip": _clip_settings,
    "set_fade_at": _on_clip,
    "set_clip_envelope": _on_clip,
    "ripple_delete": _range,
    "mute_ranges": lambda a, c: ({"track": c.track(a.get("track_id")),
                                  "count": _count(a, "ranges")}, "", None),
    "set_gate": _on_track,
    "add_gate_range": lambda a, c: ({"track": c.track(a.get("track_id")),
                                     "at": c.at(a.get("start"))}, "", None),
    "remove_gate_range": lambda a, c: ({"track": c.track(a.get("track_id")),
                                        "at": c.at(a.get("start"))}, "", None),
    "set_clips_ungated": _ungated,
    "open_gated_region": lambda a, c: ({"track": c.track(a.get("track_id")),
                                        "at": c.at(a.get("at"))}, "", None),
    "replace_clip_media": _plain,
    "add_marker": _add_marker,
    "rename_marker": _marker,
    "move_marker": _marker,
    "set_region_end": _marker,
    "delete_marker": _marker,
    "set_marker_kind": _marker,
    "add_placeholder": _placeholder,
    "edit_placeholder_text": _placeholder,
    "set_placeholder_length": _placeholder,
    "move_placeholder": _placeholder,
    "delete_placeholder": _plain,
    "replace_placeholder": _plain,
    "shift_clips": _on_clips,
    "set_clips": _clips_settings,
    "delete_clips": _on_clips,
    "mark_in_sync": _on_clips,
    "resync": _on_clips,
    "set_free": _on_clips,
    "send_home": _on_clips,
    "set_sync_anchor": _on_clip,
    "split_clips": _on_clips,
    "mute_range": _range,
    "cut_range": _range,
    "nudge_clips": _on_clips,
    "move_clips_to_track": _on_clips,
    "trim_clips": _on_clips,
    "adjust_clip_gain": _clip_gain,
    "restore_cuts": _on_clips,
    "roll_trim": _on_clip,
    "ripple_trim": _on_clip,
    "group_clips": _on_clips,
    "ungroup_clips": _on_clips,
    "merge_clips": _on_clips,
    "restore": _plain,  # named from its target, below
}


def describe(op: dict | None, state: Project, *, label: str = "",
             target: dict | None = None) -> dict[str, Any]:
    """The readable name of a step made by ``op``. ``label``: the stored label, used
    when no describer knows the op. ``target``: for a restore, the restored step's
    ``{"op", "label"}`` (a restore of a restore is named after the first target)."""
    op = op or {}
    name = op.get("name")
    args = op.get("args") if isinstance(op.get("args"), dict) else {}
    describer = DESCRIBERS.get(name) if isinstance(name, str) else None
    if describer is None:
        return {"name": label or str(name or ""), "base": label or str(name or ""),
                "detail": "", "run": None}
    if name == "restore":
        inner = describe((target or {}).get("op"), state,
                         label=(target or {}).get("label") or "")
        what = inner["name"] or t("history.op.a_step")
        base = t("history.op.restore", target=what)
        return {"name": base, "base": base, "detail": "", "run": None}
    context = _Context(state)
    try:
        values, detail, obj = describer(args, context)
    except (TypeError, ValueError, AttributeError):  # odd arguments from an old file
        values, detail, obj = {}, "", None
    base = t(f"history.op.{name}", **values)
    if "{" in base:  # a value the message names but the describer could not give
        base = t(f"history.op.{name}", **{**_BLANKS, **values})
    full = f"{base} · {detail}" if detail else base
    return {"name": full, "base": base, "detail": detail,
            "run": f"{name}:{obj}" if obj is not None else None}


#: Words for values a message may name when the arguments lacked them.
_BLANKS: dict[str, Any] = {"track": "?", "where": "?", "at": "?", "length": "?",
                           "delta": "?", "name": "?", "marker": "?", "bus": "?",
                           "text": "?", "count": 1, "state": "?"}
