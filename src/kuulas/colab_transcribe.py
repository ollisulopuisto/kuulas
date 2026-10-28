"""Transcribe on Google Colab from inside kuulas (WP78).

kuulas runs the owner's ``colab-transcribe`` tool (podcast repo) on audio files
as they are, with no ``.nhsx`` and no Hindenburg session, and reads the word
lists it writes. The audio leaves the computer (Colab, and Drive unless
``--no-drive``): the UI says so before the first use, and nothing here starts
without a job the user asked for.

The contract kuulas asks of the tool::

    colab-transcribe --audio F [--audio F ...] --json FOLDER --progress
                     [--model M] [--language L] [--no-drive]

* one ``FOLDER/<audio stem>.words.json`` per audio file:
  ``{"version": 1, "timing": "whisper" | "orukeet" | "ctc-v1", "language": "fi",
  "words": [{"w": text, "s": seconds, "e": seconds}]}``, seconds from the audio
  file's start, words in start order;
* ``--progress`` prints ``PROGRESS <0-100> <message>`` lines; exit 0 on success,
  non-zero with the reason in the last lines of output;
* SIGTERM cancels (the process group gets it, then SIGKILL after a grace time).

The result files are named by the audio file's stem, so two files with one stem
in one run are refused. ``read_words_json`` is strict on purpose: unlike
``transcribe.parse`` it takes only this shape and names the first fault, because
a wrong word time would silently misplace every cut made from the text.

The process runner is injectable so a test can use a fake script.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

from .automix import _signal
from .automix import run_process as _run_process
from .clock import FLICKS
from .jobs import JobCancelledError
from .messages import KuulasError, t
from .processes import kill_process_group

log = logging.getLogger("kuulas.colab_transcribe")

_REMOTE_COMMAND = [
    "uvx", "--python", "3.13",
    "--overrides", str(Path(__file__).with_name("transcription-overrides.txt")),
    "--from",
    "git+https://github.com/ollisulopuisto/podcast@c5ea1985bdc6e31aff860aa5f69600c44e94f65e#subdirectory=colab-transcribe",
    "colab-transcribe"]
DEFAULT_MODEL = "turbo"
#: The log kept for the UI, and the part of it an error carries.
LOG_LINES = 200
TAIL_LINES = 15
#: Results files the tool writes, by audio stem.
RESULT_SUFFIX = ".words.json"
#: How the word times were made: ``whisper`` (as Whisper gave them) or ``ctc-v<N>`` (the
#: starts corrected by the forced aligner, alignment version N; the number changes when
#: its rule or model does, so a later version must not be refused).
_TIMING = re.compile(r"whisper|orukeet|ctc-v[0-9]+")
#: The Colab CLI's own update notice: noise in a progress line or an error text.
_NOISE = re.compile(
    r"^\[colab\] (A new version of Colab CLI|Run 'colab update'|To silence this check)")
#: A Colab session the tool kept by name ('whisper') that has died on Google's side.
_SESSION_LOST = re.compile(r"Session '[^']*' appears to be lost")
#: One structured event per line, after this prefix, as JSON (the tool's --events, the
#: same protocol as the automixer's, docs/PODCAST-MAGIC.md "Live events").
EVENT_PREFIX = "@@kuulas "
#: Seconds to wait after SIGINT (the tool stops its Colab session on it) before SIGTERM.
SESSION_STOP_SECONDS = 30
_PROGRESS = re.compile(r"PROGRESS\s+(\d{1,3})(?:\s+(.*))?$")

def _stop_session(proc: subprocess.Popen) -> int:
    """Cancel: SIGINT first (the tool stops its Colab session on it; SIGTERM is not
    handled, so a plain terminate would leave the session billing), then SIGTERM, then
    SIGKILL."""
    for sig, wait in ((signal.SIGINT, SESSION_STOP_SECONDS), (signal.SIGTERM, 10)):
        _signal(proc, sig)
        try:
            return proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            continue
    kill_process_group(proc)
    return proc.wait()


def run_process(cmd, cwd, on_line, cancel):
    """``automix.run_process`` with the cancel that stops the Colab session."""
    return _run_process(cmd, cwd, on_line, cancel, stop=_stop_session)


RunProcess = Callable[
    [list[str], str | None, Callable[[str], None], threading.Event], int
]
Report = Callable[..., None]


def default_command(repo_root: Path | None = None) -> list[str]:
    """Use the adjacent podcast checkout in development, the public tool otherwise."""
    root = repo_root or Path(__file__).resolve().parents[2]
    local_project = root.parent / "podcast" / "colab-transcribe"
    if (local_project / "pyproject.toml").is_file():
        return ["uv", "run", "--project", str(local_project), "colab-transcribe"]
    return list(_REMOTE_COMMAND)


class ColabError(KuulasError, RuntimeError):
    """A failed Colab transcription (a message key, so the job shows it translated)."""


# -- settings ----------------------------------------------------------------------------


def _words(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(x, str) and x for x in value)


def resolve_settings(stored: dict | None) -> dict[str, Any]:
    """The settings with defaults filled in: ``command`` (list), ``cwd`` (folder or
    None: run where kuulas runs), ``extra_args`` (list), ``no_drive`` (bool, default
    true: the audio is sent straight to the Colab VM, not through Drive), ``model``
    and ``language`` (None: the tool's own choice)."""
    stored = stored or {}
    command = stored.get("command")
    extra = stored.get("extra_args")
    cwd = stored.get("cwd")
    model = stored.get("model")
    language = stored.get("language")
    no_drive = stored.get("no_drive")
    align = stored.get("align")
    return {
        "command": list(command) if _words(command) else default_command(),
        "cwd": cwd.strip() if isinstance(cwd, str) and cwd.strip() else None,
        "extra_args": list(extra) if isinstance(extra, list)
        and all(isinstance(x, str) for x in extra) else [],
        "no_drive": no_drive if isinstance(no_drive, bool) else False,
        # The podcast tool corrects the word starts after Whisper with --align: on by
        # default; the result says which it is (`timing`).
        "align": align if isinstance(align, bool) else True,
        "model": model.strip() if isinstance(model, str) and model.strip()
        else DEFAULT_MODEL,
        "language": language.strip() if isinstance(language, str) and language.strip()
        else None,
    }


def settings_path() -> Path:
    """``$KUULAS_COLAB_FILE`` (tests) or ``colab.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_COLAB_FILE")
    if override:
        return Path(override)
    from .desktop import config_dir  # noqa: PLC0415 - desktop imports the session

    return config_dir() / "colab.json"


def load_settings() -> dict:
    """The stored settings (any subset); empty when missing or damaged."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> dict:
    """Check and store the settings (atomic write); returns what was stored.
    Raises ``ColabError`` (``error.colab.bad_settings``) for a wrong shape."""
    command, cwd, extra, no_drive, model, language, align = (settings.get(k) for k in (
        "command", "cwd", "extra_args", "no_drive", "model", "language", "align"))
    ok = command is None or _words(command)
    ok = ok and all(v is None or isinstance(v, str) for v in (cwd, model, language))
    ok = ok and all(v is None or isinstance(v, bool) for v in (no_drive, align))
    ok = ok and (extra is None or (isinstance(extra, list)
                                   and all(isinstance(x, str) for x in extra)))
    if not ok:
        raise ColabError("error.colab.bad_settings")
    keys = ("command", "cwd", "extra_args", "no_drive", "model", "language", "align")
    clean = {k: settings[k] for k in keys if settings.get(k) is not None}
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:
        raise ColabError("error.export.cannot_write", path=str(path),
                         error=str(e)) from e
    return clean


# -- the command and the result ----------------------------------------------------------


#: Commands that refused ``--events`` (an older tool): not asked again in this process.
_NO_EVENTS: set[tuple] = set()


def forget_event_support() -> None:
    """Forget which tools refused ``--events`` (tests; a tool that was updated)."""
    _NO_EVENTS.clear()


def _refused_events(tail: str) -> bool:
    """Did the tool answer that it does not know ``--events`` (argparse's wording)?"""
    return "unrecognized arguments" in tail and "--events" in tail


def build_command(settings: dict, audio: list[Path], folder: Path, *,
                  model: str, language: str | None, events: bool = False) -> list[str]:
    """The argument list (never a shell string): the command, ``--audio`` per file,
    ``--json`` folder, ``--progress``, the model and language, ``--align`` (the word-start
    correction, on by default), ``--no-drive`` when set,
    then the user's extra arguments."""
    cmd = [*settings["command"]]
    for path in audio:
        cmd += ["--audio", str(path)]
    cmd += ["--json", str(folder), "--progress", "--model", model]
    if events:
        cmd.append("--events")
    if language:
        cmd += ["--language", language]
    if settings.get("align", True):
        cmd.append("--align")
    if settings.get("no_drive"):
        cmd.append("--no-drive")
    return [*cmd, *settings["extra_args"]]


def _seconds(value: object) -> float | None:
    """A finite JSON number, else None (a bool is not a time)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def read_words_json(path: Path | str) -> dict:
    """Read one ``<stem>.words.json`` strictly: ``{"words" (stored words, flicks),
    "timing", "language"}``. Raises ``ColabError`` with one key per fault:
    ``result_unreadable``, ``result_version``, ``result_timing``, ``result_words``,
    ``result_word`` (missing or wrongly typed field, empty text), ``result_negative``,
    ``result_end_before_start``, ``result_order`` (a start before the previous start).
    A word that ends where it starts still gets one flick (as ``transcribe.parse``)."""
    def fail(key: str, **params) -> NoReturn:
        raise ColabError(key, **params)

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        fail("error.colab.result_unreadable", error=str(e))
    if not isinstance(data, dict):
        fail("error.colab.result_unreadable", error="not a JSON object")
    if data.get("version") != 1 or isinstance(data.get("version"), bool):
        fail("error.colab.result_version", version=data.get("version"))
    timing = data.get("timing")
    if not (isinstance(timing, str) and _TIMING.fullmatch(timing)):
        fail("error.colab.result_timing", timing=timing)
    raw = data.get("words")
    if not isinstance(raw, list):
        fail("error.colab.result_words")
    words = []
    previous = 0.0
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            fail("error.colab.result_word", index=index, field="word")
        text = item.get("w")
        if not isinstance(text, str) or not text.strip():
            fail("error.colab.result_word", index=index, field="w")
        start, end = _seconds(item.get("s")), _seconds(item.get("e"))
        if start is None:
            fail("error.colab.result_word", index=index, field="s")
        if end is None:
            fail("error.colab.result_word", index=index, field="e")
        if start < 0 or end < 0:
            fail("error.colab.result_negative", index=index)
        if end < start:
            fail("error.colab.result_end_before_start", index=index)
        if start < previous:
            fail("error.colab.result_order", index=index)
        previous = start
        s = round(start * FLICKS)
        words.append({"w": text.strip(), "s": s, "e": max(s + 1, round(end * FLICKS)),
                      "spk": ""})
    language = data.get("language")
    rejected = data.get("rejected")
    return {"words": words, "timing": timing,
            "language": language if isinstance(language, str) else "",
            "rejected": rejected if isinstance(rejected, int)
            and not isinstance(rejected, bool) and rejected >= 0 else 0}


# -- running -----------------------------------------------------------------------------


def _stage_text(event: dict) -> str:
    """What a stage that has started is told as: the file it is on for `transcribe` and
    `align`, which the tool does one file at a time."""
    stage = str(event.get("stage") or "")
    name, index, total = event.get("name"), event.get("index"), event.get("total")
    if stage in ("transcribe", "align") and name:
        return t(f"ui.colab.stage.{stage}_named", name=name, index=index, total=total)
    if stage in ("transcribe", "align") and index and total:
        return t(f"ui.colab.stage.{stage}", index=index, total=total)
    key = f"ui.colab.stage.{stage}"
    return t(key) if stage else ""


def run(items: list[dict], params: dict, settings: dict, report: Report,
        cancel: threading.Event, run_process: RunProcess = run_process) -> dict:
    """Run the tool on ``items`` (``{"id", "name", "path"}``: the audio file as it is)
    in ONE call and read every result. ``params``: ``model`` and ``language``
    (replace the settings for this run), ``extra_args``. Returns ``{"results":
    {id: {"words", "timing", "language"}}, "log", "command"}``. Raises ``ColabError``
    or ``JobCancelledError`` after cancel; the temporary folder is removed in every
    case. ``report(fraction, message="", indeterminate=False)``."""
    settings = resolve_settings(settings)
    if isinstance(params.get("extra_args"), list):
        settings["extra_args"] = [str(x) for x in params["extra_args"]]
    model = params.get("model") or settings["model"]
    language = params.get("language") or settings["language"]
    if settings["cwd"] and not Path(settings["cwd"]).is_dir():
        raise ColabError("error.colab.bad_cwd", cwd=settings["cwd"])
    stems = [Path(i["path"]).stem for i in items]
    if len(set(stems)) != len(stems):
        dup = sorted({s for s in stems if stems.count(s) > 1})
        raise ColabError("error.colab.duplicate_names", names=", ".join(dup))

    lines: deque[str] = deque(maxlen=LOG_LINES)
    try:
        # mkdtemp: private to the user (0700), in the system's temporary folder.
        scratch = Path(tempfile.mkdtemp(prefix="kuulas-colab-"))
    except OSError as e:
        raise ColabError("error.colab.temp", error=str(e)) from e
    try:
        # Ask for the tool's structured events; a tool that does not know the flag says so
        # at once and is run again without it (and not asked again).
        key = (tuple(settings["command"]), settings["cwd"])
        use_events = key not in _NO_EVENTS
        cmd = build_command(settings, [Path(i["path"]) for i in items], scratch,
                            model=model, language=language, events=use_events)
        report(0.0, "", indeterminate=True)
        reached = [0.0]
        count = len(items)

        def shown(message: str) -> str:
            # The tool does one run for all files; the finished result files say
            # which file it is on.
            if count < 2:
                return message
            done = sum((scratch / f"{s}{RESULT_SUFFIX}").is_file() for s in stems)
            return f"[{min(count, done + 1)}/{count}] {message}"

        # What the tool's events said (docs/PODCAST-MAGIC.md): its own short reason for a
        # failure, and whether it saw the session lost (retried by that code, not text).
        said = {"error": None, "lost": False, "events": False}

        def on_event(event: dict) -> None:
            kind = event.get("event")
            if kind == "progress":
                share = min(100, max(0, int(event.get("percent") or 0))) / 100
                reached[0] = max(reached[0], 0.99 * share)
                report(reached[0], str(event.get("message") or ""))
            elif kind == "stage" and event.get("state") == "start":
                report(reached[0], _stage_text(event), indeterminate=reached[0] == 0.0)
            elif kind == "session" and event.get("state") in ("new", "reuse", "reset"):
                report(reached[0], t(f"ui.colab.session.{event['state']}"),
                       indeterminate=reached[0] == 0.0)
            elif kind == "warning" and event.get("code") == "session_lost":
                said["lost"] = True
            elif kind == "error":
                said["error"] = str(event.get("message") or "") or None

        def on_line(line: str) -> None:
            if not line.strip():
                return
            if line.startswith(EVENT_PREFIX):
                with contextlib.suppress(ValueError, TypeError, KeyError):
                    on_event(json.loads(line[len(EVENT_PREFIX):]))
                    said["events"] = True
                return
            lines.append(line)
            if _NOISE.match(line):
                return
            if said["events"] and _PROGRESS.match(line):
                return  # the same progress is in the events
            found = _PROGRESS.match(line)
            if found:
                share = min(100, int(found.group(1))) / 100
                reached[0] = max(reached[0], 0.99 * share)
                report(reached[0], shown((found.group(2) or "").strip() or line))
            else:
                report(reached[0], shown(line), indeterminate=reached[0] == 0.0)

        log.info("Running %s", cmd)
        while True:
            try:
                code = run_process(cmd, settings["cwd"], on_line, cancel)
            except FileNotFoundError as e:
                raise ColabError("error.colab.not_found",
                                 command=" ".join(settings["command"]),
                                 cwd=settings["cwd"] or "") from e
            if cancel.is_set():
                raise JobCancelledError
            if code != 0 and use_events and _refused_events("\n".join(lines)):
                _NO_EVENTS.add(key)
                use_events = False
                cmd = [part for part in cmd if part != "--events"]
                lines.clear()
                continue
            # The tool reuses one Colab session by name; one that died fails the run.
            # Once, ask it for a fresh session (owner, 2026-10-23, the packaged app).
            lost = said["lost"] or any(_SESSION_LOST.search(line) for line in lines)
            if code != 0 and "--reset-session" not in cmd and lost:
                cmd = [*cmd, "--reset-session"]
                said["lost"], said["error"] = False, None
                lines.append(t("ui.colab.retry_fresh"))
                report(reached[0], t("ui.colab.retry_fresh"), indeterminate=True)
                continue
            break
        tail = "\n".join([line for line in lines if not _NOISE.match(line)][-TAIL_LINES:])
        if said["error"]:
            tail = said["error"]  # the tool's own short reason, not its log
        if code != 0:
            raise ColabError("error.colab.failed", code=code, tail=tail)
        results = {}
        for item, stem in zip(items, stems, strict=True):
            file = scratch / f"{stem}{RESULT_SUFFIX}"
            if not file.is_file():
                raise ColabError("error.colab.no_result", name=item["name"], tail=tail)
            try:
                results[item["id"]] = read_words_json(file)
            except ColabError as e:
                raise ColabError(e.key, name=item["name"], **e.params) from e
        report(1.0, "")
        return {"results": results, "log": list(lines), "command": cmd}
    finally:
        with contextlib.suppress(OSError):
            shutil.rmtree(scratch, ignore_errors=True)
