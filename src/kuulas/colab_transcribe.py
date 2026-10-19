"""Transcribe on Google Colab from inside kuulas (WP78).

kuulas runs the owner's ``colab-transcribe`` tool (podcast repo) on audio files
as they are, with no ``.nhsx`` and no Hindenburg session, and reads the word
lists it writes. The audio leaves the computer (Colab, and Drive unless
``--no-drive``): the UI says so before the first use, and nothing here starts
without a job the user asked for.

The contract kuulas asks of the tool (proposed to the podcast session, not yet
measured against the real tool)::

    colab-transcribe --audio F [--audio F ...] --json FOLDER --progress
                     [--model M] [--language L] [--no-drive]

* one ``FOLDER/<audio stem>.words.json`` per audio file:
  ``{"version": 1, "timing": "whisper" | "ctc-v1", "language": "fi",
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
import tempfile
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

from .automix import run_process
from .clock import FLICKS
from .jobs import JobCancelledError
from .messages import KuulasError

log = logging.getLogger("kuulas.colab_transcribe")

DEFAULT_COMMAND = [
    "uvx", "--from",
    "git+https://github.com/ollisulopuisto/podcast#subdirectory=colab-transcribe",
    "colab-transcribe"]
DEFAULT_MODEL = "turbo"
#: The log kept for the UI, and the part of it an error carries.
LOG_LINES = 200
TAIL_LINES = 15
#: Results files the tool writes, by audio stem.
RESULT_SUFFIX = ".words.json"
TIMINGS = ("whisper", "ctc-v1")
_PROGRESS = re.compile(r"PROGRESS\s+(\d{1,3})(?:\s+(.*))?$")

RunProcess = Callable[
    [list[str], str | None, Callable[[str], None], threading.Event], int
]
Report = Callable[..., None]


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
    return {
        "command": list(command) if _words(command) else list(DEFAULT_COMMAND),
        "cwd": cwd.strip() if isinstance(cwd, str) and cwd.strip() else None,
        "extra_args": list(extra) if isinstance(extra, list)
        and all(isinstance(x, str) for x in extra) else [],
        "no_drive": no_drive if isinstance(no_drive, bool) else True,
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
    command, cwd, extra, no_drive, model, language = (settings.get(k) for k in (
        "command", "cwd", "extra_args", "no_drive", "model", "language"))
    ok = command is None or _words(command)
    ok = ok and all(v is None or isinstance(v, str) for v in (cwd, model, language))
    ok = ok and (no_drive is None or isinstance(no_drive, bool))
    ok = ok and (extra is None or (isinstance(extra, list)
                                   and all(isinstance(x, str) for x in extra)))
    if not ok:
        raise ColabError("error.colab.bad_settings")
    keys = ("command", "cwd", "extra_args", "no_drive", "model", "language")
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


def build_command(settings: dict, audio: list[Path], folder: Path, *,
                  model: str, language: str | None) -> list[str]:
    """The argument list (never a shell string): the command, ``--audio`` per file,
    ``--json`` folder, ``--progress``, the model and language, ``--no-drive`` when set,
    then the user's extra arguments."""
    cmd = [*settings["command"]]
    for path in audio:
        cmd += ["--audio", str(path)]
    cmd += ["--json", str(folder), "--progress", "--model", model]
    if language:
        cmd += ["--language", language]
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
    if timing not in TIMINGS:
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
    return {"words": words, "timing": timing,
            "language": language if isinstance(language, str) else ""}


# -- running -----------------------------------------------------------------------------


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
        cmd = build_command(settings, [Path(i["path"]) for i in items], scratch,
                            model=model, language=language)
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

        def on_line(line: str) -> None:
            if not line.strip():
                return
            lines.append(line)
            found = _PROGRESS.match(line)
            if found:
                share = min(100, int(found.group(1))) / 100
                reached[0] = max(reached[0], 0.99 * share)
                report(reached[0], shown((found.group(2) or "").strip() or line))
            else:
                report(reached[0], shown(line), indeterminate=reached[0] == 0.0)

        log.info("Running %s", cmd)
        try:
            code = run_process(cmd, settings["cwd"], on_line, cancel)
        except FileNotFoundError as e:
            raise ColabError("error.colab.not_found",
                             command=" ".join(settings["command"]),
                             cwd=settings["cwd"] or "") from e
        if cancel.is_set():
            raise JobCancelledError
        tail = "\n".join(list(lines)[-TAIL_LINES:])
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
