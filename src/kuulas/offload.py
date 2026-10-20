"""Heavy analysis in its own low-priority process (docs/PLAYBACK-PRIORITY.md).

The editor has one GIL, and the audio callback needs it every ~21 ms. Measuring
speech levels, Auto-Silence and loudness curves is seconds of numpy, scipy,
numba and libsndfile per hour of audio; on threads of the editor it kept the
callback waiting (owner's ``sample``, 2026-10-20). ``call`` runs it in
``python -m kuulas.analysis_worker`` instead: its own GIL, nice 19 and the
Darwin background band (efficiency cores, throttled IO). When the caller is
background work (a job; ``priority.is_background``), the worker is also
stopped outright (SIGSTOP) while the editor plays and continued after.

The worker gets a pickled snapshot (the frozen ``Project``, the arguments) and
reopens the project's media read-only (``MediaStore(..., resolve=False)``),
seeded with the linked paths the editor resolved. It writes the same
content-keyed caches the editor reads (``caches/analysis``), so its work is
never done twice. Only the functions in ``TASKS`` can be run.

Fail soft: a store the worker cannot reopen (a test's in-memory store) or a
worker that does not answer (cannot start, crashed) is measured in the editor,
under the gate (``priority.gated_map``, ``checkpoint``), with a log line.
``MODE = "inline"`` (tests, ``KUULAS_ANALYSIS=inline``) never starts a process.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import os
import pickle
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import priority, toolpath
from .messages import KuulasError, t

log = logging.getLogger("kuulas.offload")

#: "process" (the app) or "inline" (tests; conftest sets it).
MODE = os.environ.get("KUULAS_ANALYSIS", "process")

#: What the worker may run: ``fn(project, store, *args, **kwargs)``, pure on
#: the snapshot. A name, so the task file never names code.
TASKS: dict[str, str] = {
    "silence_ranges": "kuulas.analysis:silence_ranges",
    "raw_silence_ranges": "kuulas.analysis:raw_silence_ranges",
    "preview_silence": "kuulas.analysis:preview_silence",
    "speech_lanes": "kuulas.analysis:speech_lanes",
    "anyone_talking_intervals": "kuulas.analysis:anyone_talking_intervals",
    "project_curves": "kuulas.loudness_curve:project_curves",
}

#: How often the waiting editor thread looks at cancel and the gate.
POLL_S = 0.05


class WorkerFailedError(Exception):
    """The worker gave no answer (not an error of the analysis itself)."""


def resolve(task: str) -> Callable:
    """The function of ``task``; KeyError for anything not in ``TASKS``."""
    module, _, name = TASKS[task].partition(":")
    return getattr(importlib.import_module(module), name)


def store_spec(store) -> dict | None:
    """What the worker needs to reopen ``store`` read-only, or None when it is
    not a project's ``MediaStore`` (then the analysis runs here)."""
    from .media import MediaStore  # noqa: PLC0415 - media imports this module's users

    if not isinstance(store, MediaStore):
        return None
    return {"folder": str(store.folder), "rate": store.rate, "db": str(store.db_path),
            "cache_root": str(store.cache_root), "package_root": str(store.package_root),
            "series_root": str(store.series_root) if store.series_root else None,
            "preferences": str(store.preferences),
            "resolved": dict(store._resolved_paths), "linked_ok": dict(store._linked_ok)}


def worker_argv(task_file: Path, result_file: Path) -> list[str]:
    """``<sys.executable> -m kuulas.analysis_worker <task> <result>``. In the
    Briefcase app ``sys.executable`` is the launcher, which runs ``python -m
    kuulas`` with these arguments; ``bundle.main`` hands them to the worker."""
    return [sys.executable, "-m", "kuulas.analysis_worker", str(task_file),
            str(result_file)]


def call(task: str, project, store, *args: Any, cancel: threading.Event | None = None,
         pause: bool | None = None, **kwargs: Any) -> Any:
    """``TASKS[task](project, store, *args, **kwargs)``, in the worker process.

    ``cancel`` (default: the calling job's) kills the worker and raises
    ``CancelledError``. ``pause`` (default: whether the caller is background
    work) stops the worker while audio plays."""
    fn = resolve(task)
    spec = store_spec(store) if MODE == "process" else None
    if spec is None:
        return fn(project, store, *args, **kwargs)
    payload = {"task": task, "project": project, "store": spec, "args": args,
               "kwargs": kwargs}
    try:
        reply = _run(payload, cancel, pause)
    except WorkerFailedError as e:
        log.warning(t("log.offload.fallback", error=str(e)))
        return fn(project, store, *args, **kwargs)
    error = reply.get("error")
    if error is not None:
        raise _rebuild(error)
    return reply["value"]


def probe(what: dict, cancel: threading.Event | None = None,
          pause: bool | None = None) -> dict:
    """Ask the worker about itself (``{"what": "priority"}``) or have it spin
    (``{"what": "spin", "seconds": s}``): the selftest and the tests."""
    reply = _run({"task": "_probe", "probe": what}, cancel, pause)
    error = reply.get("error")
    if error is not None:
        raise _rebuild(error)
    return reply["value"]


def _rebuild(error: dict) -> Exception:
    """The worker's error as the editor would have raised it: a ``KuulasError``
    (of its own class when that can be found) with its key, else a failure."""
    key = error.get("key")
    if key:
        cls: type = KuulasError
        with contextlib.suppress(ImportError, AttributeError, ValueError):
            found = getattr(importlib.import_module(error["module"]), error["cls"])
            if isinstance(found, type) and issubclass(found, KuulasError):
                cls = found
        try:
            return cls(key, **(error.get("params") or {}))
        except TypeError:
            return KuulasError(key, **(error.get("params") or {}))
    return KuulasError("error.offload.failed", error=str(error.get("text", "")))


def _signal(proc: subprocess.Popen, name: str) -> None:
    sig = getattr(signal, name, None)
    if sig is not None and proc.poll() is None:
        with contextlib.suppress(OSError):
            os.kill(proc.pid, sig)


def _run(payload: dict, cancel: threading.Event | None, pause: bool | None) -> dict:
    cancel = cancel if cancel is not None else priority._cancel()
    pause = priority.is_background() if pause is None else pause
    on_pause, on_resume = priority._listener() or (None, None)
    with tempfile.TemporaryDirectory(prefix="kuulas-analysis-") as tmp:
        task, result, errors = (Path(tmp) / n for n in ("task.pickle", "result.pickle",
                                                         "stderr.txt"))
        task.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
        with errors.open("wb") as err:
            try:
                proc = subprocess.Popen(  # noqa: S603 - our own module, fixed argv
                    worker_argv(task, result), stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=err, close_fds=True,
                    env=toolpath.tool_env())
            except OSError as e:
                raise WorkerFailedError(str(e)) from e
            stopped = False
            try:
                while True:
                    try:
                        code = proc.wait(timeout=POLL_S)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if cancel is not None and cancel.is_set():
                        raise priority.CancelledError
                    # Background work: frozen while the editor plays.
                    want = pause and priority.GATE.is_playing()
                    if want != stopped:
                        _signal(proc, "SIGSTOP" if want else "SIGCONT")
                        stopped = want
                        hook = on_pause if want else on_resume
                        if hook is not None:
                            hook()
            finally:
                if stopped:
                    _signal(proc, "SIGCONT")
                    if on_resume is not None:
                        on_resume()
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        if code != 0 or not result.exists():
            tail = errors.read_bytes()[-400:].decode("utf-8", "replace").strip()
            detail = f"exit {code}: {tail}" if tail else f"exit {code}"
            raise WorkerFailedError(detail)
        try:
            return pickle.loads(result.read_bytes())  # noqa: S301 - our own child wrote it
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError) as e:
            raise WorkerFailedError(str(e)) from e
