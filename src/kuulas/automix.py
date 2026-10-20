"""Mix with the automixer from inside kuulas (WP68 step 1).

The owner's automixer (``podcast/apps/automixer``) is a command line tool that
takes audio files. This module writes the edit's stems to a temporary folder
with the real "Export all tracks" code, runs the tool on them, puts the mix
beside the project and removes the stems, so nobody handles a WAV by hand.

Nothing here knows about jobs except the cancel flag and ``JobCancelledError``;
``Session.automix`` wraps ``run`` in a job. The process runner is injectable so
a test can use a fake script (or a fake runner) and never the real automixer.

Assumptions about the tool (README, not measured): it takes the audio files as
positional arguments and decides speech or music from the file names (the
exporter already adds " MUSIC" to music stems), ``-o`` names the output WAV,
``--target-lufs``, ``--ad-spot`` and ``--ad-duration`` take numbers, it exits
non-zero on failure and prints progress lines to stdout or stderr. With
``--progress`` it prints ``PROGRESS <0-100> <message>`` lines (percentages never
fall, the last is ``PROGRESS 100 done``); any other line is only shown as the
message.
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import soundfile as sf

from . import block_level, export, export_names, music_level, plugins, toolpath
from .jobs import JobCancelledError
from .messages import KuulasError, t

log = logging.getLogger("kuulas.automix")

#: What "uv run automixer" means for the owner: run in the podcast checkout.
DEFAULT_COMMAND = ["uv", "run", "automixer"]
DEFAULT_CWD = Path("Documents") / "koodi" / "podcast"
#: Writing the stems is this much of the bar; the automixer's own run is the rest.
STEMS_SHARE = 0.4
#: The log kept for the UI, and the part of it an error carries.
LOG_LINES = 200
TAIL_LINES = 15
LUFS_RANGE = (-40.0, 0.0)
_PROGRESS = re.compile(r"PROGRESS\s+(\d{1,3})(?:\s+(.*))?$")
#: How long a terminated automixer gets to exit before it is killed.
GRACE_SECONDS = 5

#: ``(command, cwd, on_line, cancel) -> exit code``; see ``run_process``.
RunProcess = Callable[
    [list[str], str | None, Callable[[str], None], threading.Event], int
]
#: ``(fraction, message, indeterminate=...)``
Report = Callable[..., None]


class AutomixError(KuulasError, RuntimeError):
    """A failed automixer run (a message key, so the job shows it translated)."""


def resolve_settings(stored: dict | None, *, home: Path | None = None) -> dict[str, Any]:
    """The automixer settings with their defaults filled in: ``command`` (list),
    ``cwd`` (folder or None), ``extra_args`` (list of strings), ``output_dir`` (where the
    mix is written; None means beside the project's ``.kuulas`` folder) and ``temp_dir``
    (where the temporary stems go; None means the system's temporary folder, as the
    OS or ``$TMPDIR`` sets it). The default folder is the podcast checkout when it
    exists. ``options`` are the automixer's switches as settings (see ``OPTIONS``): only
    values that differ from the tool's own defaults, and only valid ones."""
    stored = stored or {}
    command = stored.get("command")
    if not (isinstance(command, list) and command
            and all(isinstance(x, str) and x for x in command)):
        command = list(DEFAULT_COMMAND)
    extra = stored.get("extra_args")
    if not (isinstance(extra, list) and all(isinstance(x, str) for x in extra)):
        extra = []
    cwd = stored.get("cwd")
    if not (isinstance(cwd, str) and cwd.strip()):
        default = (Path.home() if home is None else home) / DEFAULT_CWD
        cwd = str(default) if default.is_dir() else None
    temp = stored.get("temp_dir")
    temp = temp.strip() if isinstance(temp, str) and temp.strip() else None
    out_dir = stored.get("output_dir")
    out_dir = out_dir.strip() if isinstance(out_dir, str) and out_dir.strip() else None
    return {"command": list(command), "cwd": cwd, "extra_args": list(extra),
            "temp_dir": temp, "output_dir": out_dir,
            "options": _tolerant_options(stored.get("options"))}


def settings_path() -> Path:
    """The user's automixer settings: ``$KUULAS_AUTOMIXER_FILE`` (tests) or
    ``automixer.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_AUTOMIXER_FILE")
    if override:
        return Path(override)
    from .desktop import config_dir  # noqa: PLC0415 - desktop imports the session

    return config_dir() / "automixer.json"


def load_settings() -> dict:
    """The stored settings (``command``, ``cwd``, ``extra_args``, any subset);
    empty when the file is missing or damaged. ``resolve_settings`` fills defaults."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> dict:
    """Check and store the settings (atomic write); returns what was stored.
    Raises ``AutomixError`` (``error.automix.bad_settings``) for a wrong shape."""
    command, cwd, extra, temp, out = (settings.get(k) for k in (
        "command", "cwd", "extra_args", "temp_dir", "output_dir"))
    ok = (command is None or (isinstance(command, list) and command
                              and all(isinstance(x, str) and x for x in command)))
    ok = ok and (cwd is None or isinstance(cwd, str))
    ok = ok and (temp is None or isinstance(temp, str))
    ok = ok and (out is None or isinstance(out, str))
    ok = ok and (extra is None or (isinstance(extra, list)
                                   and all(isinstance(x, str) for x in extra)))
    if not ok:
        raise AutomixError("error.automix.bad_settings")
    keys = ("command", "cwd", "extra_args", "temp_dir", "output_dir")
    clean = {k: settings[k] for k in keys if settings.get(k) is not None}
    if settings.get("options") is not None:
        clean["options"] = normalize_options(settings["options"])
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        raise AutomixError("error.export.cannot_write", path=str(path),
                           error=str(e)) from e
    return clean


def _number(params: dict, key: str, low: float | None, high: float | None,
            *, default: float | None, above: float | None = None) -> float | None:
    value = params.get(key)
    message = "error.automix.bad_" + key
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AutomixError(message, value=value) from None
    bad = number != number or number in (float("inf"), float("-inf"))  # noqa: PLR0124 - NaN
    too_low = low is not None and number < low
    too_high = high is not None and number > high
    bad = bad or too_low or too_high
    bad = bad or (above is not None and number <= above)
    if bad:
        raise AutomixError(message, value=value)
    return number


def validate_params(params: dict) -> tuple[float, float | None, float | None]:
    """``(target_lufs, ad_spot, ad_duration)`` of a run, or ``AutomixError``."""
    return (_number(params, "target_lufs", *LUFS_RANGE, default=-16.0),
            _number(params, "ad_spot", 0, None, default=None),
            _number(params, "ad_duration", None, None, default=None, above=0))


#: What the automixer's folder route accepts (podcast repo, docs/KUULAS-INTEGRATION.md).
MANIFEST_RATE = 48000


def check_rate(session) -> None:
    """The automixer only takes 48 kHz: refuse before anything is written."""
    rate = session.history.state.rate
    if rate != MANIFEST_RATE:
        raise AutomixError("error.automix.bad_rate", rate=rate)


def check_stems(folder: Path) -> None:
    """Check the stems folder against the rules the automixer's folder route reads
    ``tracks.json`` with, so a mismatch is our error with the field named, not a
    refusal from the tool: version 1, rate 48000, start_frame 0, processing "dry",
    ``frames`` matching every file, each file's rate and channels,
    music stereo, unique names. Raises ``AutomixError`` (``bad_stems``)."""
    def fail(detail: str) -> NoReturn:
        raise AutomixError("error.automix.bad_stems", detail=detail)

    try:
        listing = json.loads((folder / "tracks.json").read_text("utf-8"))
    except (OSError, ValueError) as e:
        fail(f"tracks.json: {e}")
    for field, wanted in (("version", 1), ("rate", MANIFEST_RATE), ("start_frame", 0),
                          ("processing", "dry")):
        if listing.get(field) != wanted:
            fail(f"{field} is {listing.get(field)!r}, must be {wanted!r}")
    names: set[str] = set()
    for track in listing.get("tracks", []):
        name = track.get("name")
        if name in names:
            fail(f"duplicate track name {name!r}")
        names.add(name)
        if track.get("kind") == "music" and track.get("channels") != 2:
            fail(f"track {name!r}: music must be stereo")
        try:
            info = sf.info(folder / track["file"])
        except (OSError, KeyError, RuntimeError) as e:
            fail(f"track {name!r}: file missing or unreadable ({e})")
        if info.frames != listing.get("frames"):
            fail(f"track {name!r}: frames {info.frames} differ from "
                 f"frames {listing.get('frames')}")
        if info.samplerate != MANIFEST_RATE:
            fail(f"track {name!r}: rate {info.samplerate}")
        if info.channels != track.get("channels"):
            fail(f"track {name!r}: channels {info.channels} differ from the list")


def export_stems(session, folder: Path | str, report=None,
                 cancel: threading.Event | None = None) -> dict:
    """Write the stems for the automixer into ``folder``: the "Export all tracks"
    files (dry, equal length, 48 kHz), music as
    stereo and ``tracks.json`` as version 1. Returns the export result."""
    args = {**session.tracks_export_args({"folder": str(folder)}), "for_automixer": True}
    return export.run(session, args, report, cancel, file_name="stems")


def _shown(number: float) -> str:
    return str(int(number)) if number == int(number) else str(number)


def build_command(settings: dict, folder: Path, output: Path, *,
                  target_lufs: float, ad_spot: float | None,
                  ad_duration: float | None,
                  supported: dict[str, bool] | None = None) -> list[str]:
    """The argument list (never a shell string): the command, the stems FOLDER (the
    one with ``tracks.json``; a list of files would take the automixer's in-memory
    route), ``-o``, the options of this run, ``--progress``, the switches that differ from
    the tool's defaults (``settings["options"]``), then the user's extra arguments.
    ``supported`` (``capabilities``) leaves out gated options the tool does not know."""
    cmd = [*settings["command"], str(folder), "-o", str(output),
           "--target-lufs", _shown(target_lufs), "--progress"]
    if ad_spot is not None:
        cmd += ["--ad-spot", _shown(ad_spot)]
        if ad_duration is not None:
            cmd += ["--ad-duration", _shown(ad_duration)]
    cmd += option_flags(settings.get("options") or {}, supported)
    return [*cmd, *settings["extra_args"]]


# -- the tool's switches as settings -----------------------------------------------------
#
# Read from ``podcast/apps/automixer/src/automixer/cli_mix.py`` (argparse defaults) and
# PIPELINE.md. ``kind``: ``bool`` (a stage; when the tool default is on, the flag is the
# ``--no-<x>`` one), ``number`` (``min``/``max``), ``text`` (one argument), ``list``
# (``nargs="+"`` paths). ``parent``: the number only means something while that stage is
# on. ``minimal``: ``--minimal`` switches this stage off, so it is not sent beside it.
#: ``(key, flag, kind, default, group, extras)``
_RAW_OPTIONS: tuple[tuple[str, str, str, Any, str, dict[str, Any]], ...] = (
    ("minimal", "--minimal", "bool", False, "minimal", {}),
    ("speech_hp", "--no-speech-hp", "bool", True, "speech", {"minimal": True}),
    ("speech_peak", "--no-speech-peak", "bool", True, "speech", {"minimal": True}),
    ("speech_lev", "--no-speech-lev", "bool", True, "speech", {"minimal": True}),
    ("speech_multiband", "--speech-multiband", "bool", False, "speech", {}),
    ("speech_desmack", "--no-speech-desmack", "bool", True, "speech", {"minimal": True}),
    ("speech_desmack_sensitivity", "--speech-desmack-sensitivity", "number", 0.5,
     "speech", {"min": 0.0, "max": 1.0, "parent": "speech_desmack"}),
    ("speech_debleed", "--no-debleed", "bool", True, "debleed", {"minimal": True}),
    ("speech_rider", "--no-rider", "bool", True, "debleed", {"minimal": True}),
    ("block_level", "--no-block-level", "bool", True, "debleed", {"minimal": True}),
    ("speech_mic_duck", "--mic-duck", "bool", False, "micduck", {"minimal": True}),
    # No default in the tool's parser: it uses the measured -9 dB when this is not given.
    ("mic_duck_db", "--mic-duck-db", "number", None, "micduck",
     {"min": -60.0, "max": 0.0, "parent": "speech_mic_duck"}),
    # The tool's BED_UNDER_SPEECH_DB: where the loudest 3 s of a bed sits against the
    # speech (negative = quieter). +1 is the automixer's own value, louder than the
    # speech (the owner found it "SUPER LOUD"). Only newer automixers have the flag, so
    # it is gated (``GATED``).
    ("bed_under_speech_db", "--bed-under-speech-db", "number", 1.0, "music",
     {"min": -30.0, "max": 6.0}),
    ("music_carve", "--no-music-carve", "bool", True, "music", {"minimal": True}),
    ("music_carve_strength", "--music-carve-strength", "number", 0.5, "music",
     {"min": 0.0, "max": 1.0, "parent": "music_carve"}),
    ("music_duck", "--no-music-duck", "bool", True, "music", {"minimal": True}),
    ("music_duck_threshold", "--music-duck-threshold", "number", -30.0, "music",
     {"min": -80.0, "max": 0.0, "parent": "music_duck"}),
    ("speech_plugins", "--speech-plugins", "list", None, "plugins", {}),
    ("music_plugins", "--music-plugins", "list", None, "plugins", {}),
    ("plugin_params", "--plugin-params", "text", None, "plugins", {}),
    ("track_params", "--track-params", "text", None, "plugins", {}),
    ("plugin_state", "--plugin-state", "text", None, "plugins", {}),
)
OPTIONS: dict[str, dict[str, Any]] = {
    key: {"key": key, "flag": flag, "kind": kind, "default": default, "group": group,
          **extras}
    for key, flag, kind, default, group, extras in _RAW_OPTIONS}
#: Longest text or list the UI may send (a plug-in state can be long base64).
MAX_TEXT = 20000
MAX_ITEMS = 50


def option_specs() -> list[dict[str, Any]]:
    """The switches in dialog order, for the UI (it draws its controls from these)."""
    return [dict(spec) for spec in OPTIONS.values()]


def _bad_option(key: str, value: Any) -> NoReturn:
    raise AutomixError("error.automix.bad_option", option=key, value=str(value)[:80])


def _text(key: str, value: Any) -> str:
    """A text argument: no control characters, not shaped like a flag (it is a separate
    argument, so no shell, but the tool's parser would take ``--x`` for a switch)."""
    if not isinstance(value, str):
        _bad_option(key, value)
    value = value.strip()
    if (len(value) > MAX_TEXT or value.startswith("-")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        _bad_option(key, value)
    return value


#: The options whose items are plug-ins: typed names become the installed plug-ins' paths.
PLUGIN_KEYS = ("speech_plugins", "music_plugins")


def _plugin_path(key: str, item: str) -> str:
    """The path the tool is given for one typed plug-in: a path (has a separator) must
    exist; a name is matched to an installed plug-in (``plugins.match``). With nothing
    installed (or no scan on this platform) a name is passed on as typed, as before."""
    if plugins.looks_like_path(item):
        path = Path(item).expanduser()
        if not path.exists():
            _bad_option(key, item)
        return str(path.absolute())
    installed = plugins.list_plugins()
    if not installed:
        return item
    found = plugins.resolve(item, installed)
    if found is None:
        _bad_option(key, item)
    return found


def _option_value(spec: dict[str, Any], value: Any, resolve: bool = True) -> Any:
    """The checked value of one option, or None for 'the default' (empty); else raises."""
    key, kind = spec["key"], spec["kind"]
    if kind == "bool":
        if not isinstance(value, bool):
            _bad_option(key, value)
        return value
    if kind == "number":
        if value is None or value == "":
            return None
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            _bad_option(key, value)
        try:
            number = float(value.replace(",", ".") if isinstance(value, str) else value)
        except ValueError:
            _bad_option(key, value)
        if not (spec["min"] <= number <= spec["max"]):  # NaN fails too
            _bad_option(key, value)
        return number
    if kind == "list":
        if not isinstance(value, list) or len(value) > MAX_ITEMS:
            _bad_option(key, value)
        items = [item for item in (_text(key, item) for item in value) if item]
        if resolve and key in PLUGIN_KEYS:
            items = [_plugin_path(key, item) for item in items]
        return items or None
    return _text(key, value) or None


def normalize_options(options: Any, *, resolve: bool = True) -> dict[str, Any]:
    """The options as stored: checked, and only those that differ from the tool's
    defaults. Raises ``AutomixError`` (``bad_option``) for an unknown name or a wrong
    type, an out-of-range or non-finite number, or a text that looks like a switch."""
    if not isinstance(options, dict):
        _bad_option("options", options)
    clean: dict[str, Any] = {}
    for key, value in options.items():
        spec = OPTIONS.get(key)
        if spec is None:
            _bad_option(str(key), value)
        checked = _option_value(spec, value, resolve)
        if checked is not None and checked != spec["default"]:
            clean[key] = checked
    return clean


def _tolerant_options(options: Any) -> dict[str, Any]:
    """``normalize_options`` for what was stored earlier: a damaged entry is dropped
    so one bad value never stops the dialog from opening. Plug-ins are not looked up
    again (they were resolved when stored): a plug-in that has since moved must reach the
    tool as the path it was saved with, not vanish from the command."""
    if not isinstance(options, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in options.items():
        with contextlib.suppress(AutomixError):
            clean.update(normalize_options({key: value}, resolve=False))
    return clean


def option_flags(options: dict[str, Any],
                 supported: dict[str, bool] | None = None) -> list[str]:
    """The command-line words for the options that differ from the tool's defaults
    (checked again here: ``build_command`` takes any dict). With ``supported``, a gated
    option the tool is said not to know is left out; without it everything is sent."""
    options = _tolerant_options(options)
    if supported is not None:
        options = {k: v for k, v in options.items()
                   if k not in GATED or supported.get(k, False)}
    minimal = options.get("minimal") is True

    def active(key: str) -> bool:
        spec = OPTIONS[key]
        if minimal and spec.get("minimal"):
            return False
        return bool(options.get(key, spec["default"]))

    words: list[str] = []
    for key, spec in OPTIONS.items():
        if key not in options:
            continue
        value = options[key]
        if spec["kind"] == "bool":
            if not (minimal and spec.get("minimal")):
                words.append(spec["flag"])
        elif spec["kind"] == "number":
            if spec.get("parent") is None or active(spec["parent"]):
                words += [spec["flag"], _shown(value)]
        elif spec["kind"] == "list":
            words += [spec["flag"], *value]
        else:
            words += [spec["flag"], value]
    return words


#: Options only newer automixers accept: kuulas looks in ``--help`` before sending them.
GATED = ("bed_under_speech_db",)
#: Seconds the ``--help`` probe may take (``uv run`` can need a moment to start).
PROBE_SECONDS = 10.0
#: Automixer options whose work Kuulas can already have done in the edit: option
#: key -> (the ``Project.mix_done`` entry, its field holding the option's value).
#: A number option (the beds' level) names the field. A stage switch (block
#: levelling) names ``None``: the entry says ``applied`` and the value to send is
#: ``False``, the stage off, because Kuulas did it. The music duck joins the same way.
DONE_IN_KUULAS: dict[str, tuple[str, str | None]] = {
    "bed_under_speech_db": ("bed_level", "offset_db"),
    "block_level": ("block_level", None),
}

#: How each entry is checked as still holding (``bed_level_current`` for the beds).
_STILL_HOLDS: dict[str, Callable[[Any], Any]] = {
    "bed_level": music_level.bed_level_current,
    "block_level": block_level.block_level_current,
}


def done_in_kuulas(p) -> dict[str, dict[str, Any]]:
    """``{mix_done name: {option, value, offset_db, ..., current}}`` for what the
    edit records as done. ``value`` is what the option is sent as (the offset for a
    number, ``False`` for a stage). ``current`` is False when the project changed
    since (the record no longer holds); the dialog then only hints."""
    out: dict[str, dict[str, Any]] = {}
    for option, (name, field) in DONE_IN_KUULAS.items():
        entry = (p.mix_done or {}).get(name)
        if not isinstance(entry, dict):
            continue
        if field is None:
            if entry.get("applied") is not True:
                continue
            value: Any = False
        elif (isinstance(entry.get(field), int | float)
              and not isinstance(entry[field], bool)):
            value = entry[field]
        else:
            continue
        out[name] = {"option": option, "value": value,
                     "offset_db": value if field else None,
                     "speech_lufs": entry.get("speech_lufs"),
                     "bed_lufs": entry.get("bed_lufs"), "mode": entry.get("mode"),
                     "blocks": entry.get("blocks"), "set_at": entry.get("set_at"),
                     "current": _STILL_HOLDS[name](p) is not None}
    return out


def _done_text(name: str, sent: Any) -> str:
    if name == "block_level":
        return "block level"
    return f"music level {_shown(sent)} dB"


def done_lines(p, options: dict[str, Any]) -> list[str]:
    """The log header lines for options sent with the value Kuulas set, while
    the record still holds."""
    lines = []
    for name, info in done_in_kuulas(p).items():
        sent = options.get(info["option"])
        # ``False == 0``: a stage's value only matches a boolean, a number a number.
        same = (isinstance(sent, bool) == isinstance(info["value"], bool)
                and isinstance(sent, bool | int | float) and sent == info["value"])
        if info["current"] and same:
            when = f" (set at {info['set_at']})" if info["set_at"] else ""
            lines.append(f"Done in Kuulas: {_done_text(name, sent)}{when}")
    return lines


_capability_cache: dict[tuple, dict[str, bool]] = {}
_capability_lock = threading.Lock()


def clear_capability_cache() -> None:
    with _capability_lock:
        _capability_cache.clear()


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _probe_key(command: list[str], cwd: str | None) -> tuple:
    """Command, folder and the age of what could change its answer: the program and, in
    the owner's checkout, the tool's own parser file (``uv run`` hides it)."""
    program = toolpath.resolve(command[0]) if command else None
    cli = (Path(cwd) / "apps" / "automixer" / "src" / "automixer" / "cli_mix.py"
           if cwd else None)
    return (tuple(command), cwd or "", _mtime(Path(program)) if program else None,
            _mtime(cli) if cli else None)


def capabilities(command: list[str], cwd: str | None, *,
                 run_process: RunProcess | None = None,
                 timeout: float = PROBE_SECONDS) -> dict[str, bool]:
    """Which gated options the installed automixer accepts, from its ``--help`` text.
    Never raises: a tool that cannot be run, fails or hangs (``timeout``) gives False for
    all (the option is then not sent, and the run itself reports a missing tool). Cached
    for the session per command, folder and program age."""
    key = _probe_key(command, cwd)
    with _capability_lock:
        if key in _capability_cache:
            return dict(_capability_cache[key])
    runner = run_process or globals()["run_process"]
    text: list[str] = []
    cancel = threading.Event()
    timer = threading.Timer(timeout, cancel.set)
    timer.daemon = True
    timer.start()
    code: int | None = None
    try:
        code = runner([*command, "--help"], cwd, text.append, cancel)
    except Exception:  # noqa: BLE001 - never fatal: the probe only gates a flag
        log.info("automixer --help probe failed", exc_info=True)
    finally:
        timer.cancel()
    help_text = "\n".join(text) if code == 0 and not cancel.is_set() else ""
    found = {k: OPTIONS[k]["flag"] in help_text for k in GATED}
    with _capability_lock:
        _capability_cache[key] = found
    return dict(found)


def gate_options(options: dict[str, Any], command: list[str], cwd: str | None, *,
                 run_process: RunProcess | None = None,
                 ) -> tuple[dict[str, Any], list[str]]:
    """``options`` without the gated ones the installed automixer does not accept, and a
    translated warning for each one dropped. Probes only when a gated option is set."""
    wanted = [k for k in GATED if k in options]
    if not wanted:
        return options, []
    found = capabilities(command, cwd, run_process=run_process)
    dropped = [k for k in wanted if not found.get(k)]
    kept = {k: v for k, v in options.items() if k not in dropped}
    return kept, [t("warn.automix.option_unsupported") for _ in dropped]


def _tool_env() -> dict[str, str]:
    """The environment for the tool: ours without ``VIRTUAL_ENV`` (it belongs to kuulas's
    own environment and makes ``uv run`` in the automixer's checkout warn that it will be
    ignored) and with the usual install folders on ``PATH`` (an app started from Finder
    has none of Homebrew's or ``~/.local/bin``)."""
    return toolpath.tool_env()


_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b")


def clean_output_line(line: str) -> str:
    """A tool's output line as plain text: terminal colour, erase and title codes removed
    (progress bars print them), and only what follows the last carriage return kept."""
    return _ANSI.sub("", line.rsplit("\r", 1)[-1])


def run_process(cmd: list[str], cwd: str | None, on_line: Callable[[str], None],
                cancel: threading.Event,
                stop: Callable[[subprocess.Popen], int] | None = None) -> int:
    """Run ``cmd`` without a shell, feeding each output line (stdout and stderr
    together) to ``on_line``. When ``cancel`` is set the whole process group is
    terminated (``uv run`` starts a child that a plain terminate would orphan).
    Returns the exit code; ``FileNotFoundError`` if the program is missing."""
    # Resolved to an absolute path first: the program is found even when the app's own
    # PATH lacks its folder; a missing one stays a FileNotFoundError for the caller.
    found = toolpath.resolve(cmd[0]) if cmd else None
    if found:
        cmd = [found, *cmd[1:]]
    proc = subprocess.Popen(  # noqa: S603 - an argument list from settings, no shell
        cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
        start_new_session=True, env=_tool_env())

    def read() -> None:
        if proc.stdout is None:
            raise AutomixError("error.automix.failed")
        for line in proc.stdout:
            on_line(clean_output_line(line.rstrip("\r\n")))

    reader = threading.Thread(target=read, daemon=True, name="kuulas-automix-log")
    reader.start()
    try:
        while True:
            try:
                code = proc.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                if cancel.is_set():
                    code = (stop or _stop)(proc)
                    break
    finally:
        if proc.poll() is None:  # an exception in this thread: never leave it running
            (stop or _stop)(proc)
    reader.join(timeout=5)
    return code


def _signal(proc: subprocess.Popen, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, sig)


def _stop(proc: subprocess.Popen) -> int:
    _signal(proc, signal.SIGTERM)
    try:
        return proc.wait(timeout=GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _signal(proc, signal.SIGKILL)
        return proc.wait()


def _flags_file(output: Path) -> Path:
    """Where the automixer writes its "places to listen to" for ``-o output``: the
    output's name without its extension, plus " flags.txt" (seen on the real tool)."""
    return output.with_name(f"{output.stem} flags.txt")


def _keep_flags(partial: Path, final: Path) -> str | None:
    """Rename the automixer's flags file beside the mix when it has something in it,
    else remove it. Returns the kept file's path."""
    flags = _flags_file(partial)
    try:
        text = ""
        if flags.is_file():
            text = flags.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            kept = final.with_name(f"{final.stem} flags.txt")
            os.replace(flags, kept)
            return str(kept)
        flags.unlink(missing_ok=True)
    except OSError:
        log.warning("could not tidy the automixer's flags file %s", flags)
    return None


#: The lines worth showing without opening the log: how far the music was raised, the
#: mastering result and the number of places to listen to.
_KEY_LINE = re.compile(r"\b(beds:|mastered:)|places to listen", re.IGNORECASE)


def key_lines(lines) -> list[str]:
    """The automixer's output lines that say what it did to the mix."""
    return [line.strip() for line in lines if _KEY_LINE.search(line)]


def _kuulas_version() -> str:
    try:
        return importlib.metadata.version("kuulas")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _write_log(target: Path, *, project: str, cmd: list[str], cwd: str | None,
               lines, code: int | None, started: datetime, took: dict[str, float],
               outcome: str, done: list[str] | None = None) -> str | None:
    """Write the automixer's whole output beside the mix, under a header that says what
    was run, and a summary. Never overwrites a file; ``target`` is only the name wanted.
    Returns the path, or None when it could not be written (the mix matters more than
    its log, so this only warns). The home folder is NOT shortened here: the file is the
    record, the screen is where paths are tidied."""
    kept = _unique(target.parent, target.name)
    header = [
        f"kuulas {_kuulas_version()}",
        f"date: {started.isoformat(timespec='seconds')}",
        f"project: {project}",
        f"folder: {cwd or ''}",
        f"command: {shlex.join(str(c) for c in cmd)}",
        *(done or []),
    ]
    footer = [
        f"exit code: {'none' if code is None else code}",
        f"result: {outcome}",
        *(f"{name}: {seconds:.1f} s" for name, seconds in took.items()),
    ]
    text = "\n\n".join(["\n".join(header), "\n".join(lines), "\n".join(footer)]) + "\n"
    try:
        kept.write_text(text, encoding="utf-8")
    except OSError:
        log.warning("could not write the automixer's log %s", kept)
        return None
    return str(kept)


def _unique(folder: Path, name: str) -> Path:
    target = folder / name
    n = 2
    while target.exists():
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return target


def run(session, params: dict, settings: dict, report: Report,
        cancel: threading.Event, run_process: RunProcess = run_process) -> dict:
    """Export the stems, run the automixer, return ``{"path", "name", "log",
    "command"}``. ``params``: ``target_lufs`` (default -16), ``ad_spot``,
    ``ad_duration`` (seconds), ``extra_args`` (replaces the setting for this
    run). ``report(fraction, message="", indeterminate=False)`` says how far
    it is. Raises ``AutomixError``, or ``JobCancelledError`` after cancel; the
    temporary folder and any partial output are removed in every case."""
    lufs, ad_spot, ad_duration = validate_params(params)
    check_rate(session)
    settings = resolve_settings(settings)
    if isinstance(params.get("extra_args"), list):
        settings["extra_args"] = [str(x) for x in params["extra_args"]]
    if isinstance(params.get("options"), dict):
        settings["options"] = normalize_options(params["options"])
    if settings["cwd"] and not Path(settings["cwd"]).is_dir():
        raise AutomixError("error.automix.bad_cwd", cwd=settings["cwd"])

    lines: deque[str] = deque(maxlen=LOG_LINES)
    temp_dir = settings.get("temp_dir")
    if temp_dir and not Path(temp_dir).is_dir():
        raise AutomixError("error.automix.bad_temp_dir", path=temp_dir)
    # mkdtemp makes the folder private to the user (0700), in the chosen folder or, by
    # default, wherever the system's temporary folder is.
    try:
        scratch = Path(tempfile.mkdtemp(prefix="kuulas-automix-", dir=temp_dir or None))
    except OSError as e:
        raise AutomixError("error.automix.bad_temp_dir", path=temp_dir or "") from e
    partial: Path | None = None
    began = time.monotonic()
    try:
        report(0.0, "")
        try:
            done = export_stems(
                session, scratch,
                lambda fraction, message="": report(STEMS_SHARE * fraction, message),
                cancel)
        except export.ExportError:
            if cancel.is_set():
                raise JobCancelledError from None
            raise
        listing = json.loads((Path(done["path"]) / "tracks.json").read_text("utf-8"))
        stems = Path(done["path"])
        if not any(t["audible"] for t in listing["tracks"]):
            raise AutomixError("error.automix.no_audible")
        check_stems(stems)

        # Beside the .kuulas package (never inside it: it is a registered file type, and
        # not in the remembered export folder, which may sit in a synced folder), unless
        # the settings name another folder.
        out_dir = settings.get("output_dir")
        folder = Path(out_dir) if out_dir else Path(session.package.path).parent
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise AutomixError("error.export.cannot_write", path=str(folder),
                               error=str(e)) from e
        stamp = export_names.stamp(datetime.now(UTC).astimezone())
        # Project first, the edit only when it is not the main one (export_names).
        title = listing.get("title") or listing["edit"]
        final = _unique(folder, export._safe(f"{title} automixer {stamp}.wav"))
        partial = final.with_name(f"{final.stem}.partial{final.suffix}")
        kept, warnings = gate_options(settings.get("options") or {}, settings["command"],
                                      settings["cwd"], run_process=run_process)
        settings = {**settings, "options": kept}
        done = done_lines(session.state, kept)
        lines.extend(f"kuulas: {w}" for w in warnings)
        cmd = build_command(settings, stems, partial, target_lufs=lufs,
                            ad_spot=ad_spot, ad_duration=ad_duration)
        report(STEMS_SHARE, "", indeterminate=True)
        started = datetime.now(UTC).astimezone()
        stems_took = time.monotonic() - began
        project_name = str(title)

        reached = [STEMS_SHARE]  # the bar never goes back, whatever the tool prints

        def on_line(line: str) -> None:
            if not line.strip():
                return
            lines.append(line)
            found = _PROGRESS.match(line)
            if found:  # "PROGRESS 40 message"; the last is "PROGRESS 100 done"
                share = min(100, int(found.group(1))) / 100
                reached[0] = max(
                    reached[0], STEMS_SHARE + (1 - STEMS_SHARE) * 0.99 * share
                )
                report(reached[0], (found.group(2) or "").strip() or line)
            else:  # any other line is only the message
                report(reached[0], line, indeterminate=reached[0] == STEMS_SHARE)

        log.info("Running %s", cmd)
        ran = time.monotonic()
        code: int | None = None

        def fail(error: AutomixError) -> NoReturn:
            # Kept beside where the mix would have been, so a failure can be diagnosed.
            kept = _write_log(
                final.with_name(f"{final.stem} FAILED log.txt"), project=project_name,
                cmd=cmd, cwd=settings["cwd"], lines=lines, code=code, started=started,
                took={"stems": stems_took, "automixer": time.monotonic() - ran},
                outcome=f"failed: {error.key}", done=done)
            error.params["log_file"] = kept or ""
            raise error

        try:
            code = run_process(cmd, settings["cwd"], on_line, cancel)
        except FileNotFoundError as e:
            lines.append(f"not found: {e}")
            fail(AutomixError("error.automix.not_found",
                              command=" ".join(settings["command"]),
                              cwd=settings["cwd"] or ""))
        if cancel.is_set():
            raise JobCancelledError
        if code != 0:
            fail(AutomixError("error.automix.failed", code=code,
                              tail="\n".join(list(lines)[-TAIL_LINES:])))
        if not partial.is_file():
            fail(AutomixError("error.automix.no_output",
                              tail="\n".join(list(lines)[-TAIL_LINES:])))
        flags = _keep_flags(partial, final)
        os.replace(partial, final)
        partial = None
        kept_log = _write_log(
            final.with_name(f"{final.stem} log.txt"), project=project_name, cmd=cmd,
            cwd=settings["cwd"], lines=lines, code=code, started=started,
            took={"stems": stems_took, "automixer": time.monotonic() - ran},
            outcome=f"mixed: {final.name}", done=done)
        report(1.0, "")
        return {"path": str(final), "name": final.name, "log": list(lines),
                "command": cmd, "flags": flags, "log_file": kept_log,
                "warnings": warnings, "summary": [*warnings, *key_lines(lines)]}
    finally:
        if partial is not None:
            with contextlib.suppress(OSError):
                partial.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                _flags_file(partial).unlink(missing_ok=True)
        shutil.rmtree(scratch, ignore_errors=True)
