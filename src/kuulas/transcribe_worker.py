"""The detached transcription worker (WP79): ``kuulas-worker run <job file>``.

Started by the editor in its own session (``bgjobs.launch_worker``), so it keeps
going when the window, the app or the project is closed. It reads the job file,
runs the engine (faster-whisper here, or ``colab-transcribe`` through the WP78
runner), keeps ``<id>.status.json`` current and writes one
``<id>.<media>.words.json`` per media. It never opens the project database or
takes its lock: the editor ingests the results (``Session``).

Cancel: SIGTERM/SIGINT, or the editor's ``<id>.cancel`` file (polled). Both stop
the engine the same way (the Colab runner stops its Colab session). A worker that
is killed or lost with the machine leaves a ``running`` status with a dead pid,
which the editor shows as "interrupted".

Imports only ``bgjobs``, ``transcribe`` and ``colab_transcribe``, never the session.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import bgjobs, colab_transcribe, transcribe
from .jobs import JobCancelledError
from .messages import KuulasError, t
from .package import write_json_atomic

log = logging.getLogger("kuulas.worker")

#: Status writes are at most this far apart (every one is sync traffic in a
#: Dropbox project); state changes are written at once.
STATUS_INTERVAL_S = 1.0
CANCEL_POLL_S = 0.2
LOG_KEPT = 20


class _Status:
    """``<id>.status.json``, replaced atomically; throttled unless forced."""

    def __init__(self, path: Path, interval: float):
        self.path, self.interval = path, interval
        self.lock = threading.Lock()
        self.data: dict = {"state": "queued", "progress": 0.0, "message": "",
                           "indeterminate": True, "log": [], "pid": os.getpid(),
                           "host": bgjobs._hostname(), "started": bgjobs.now_iso(),
                           "finished": None, "error": None}
        self.last = 0.0
        self.dirty = False
        self.lines: collections.deque[str] = collections.deque(maxlen=LOG_KEPT)

    def update(self, *, force: bool = False, **fields) -> None:
        with self.lock:
            self.data.update(fields)
            self.data["log"] = list(self.lines)
            now = time.monotonic()
            if not force and now - self.last < self.interval:
                self.dirty = True  # ``flush_due`` writes it once the interval is up
                return
            self._write(now)

    def _write(self, now: float) -> None:
        self.last, self.dirty = now, False
        try:
            write_json_atomic(self.path, self.data)
        except OSError as e:  # a full disk must not kill a long transcription
            log.warning("cannot write %s: %s", self.path, e)

    def flush_due(self) -> None:
        """Write a change that arrived inside the interval (else the last progress
        line of a quiet engine would never show)."""
        with self.lock:
            if self.dirty and time.monotonic() - self.last >= self.interval:
                self._write(time.monotonic())

    def line(self, message: str) -> None:
        if message:
            self.lines.append(message)


class _KeepAwake:
    """macOS: ``caffeinate -i -m -w <our pid>`` while a job runs, like the recorder's
    (``kuulas_recorder.power``; the editor package may not import the recorder but its
    client, so this is a small copy). ``-w`` ends it with this process, even after a
    SIGKILL. Other systems: nothing yet."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        tool = shutil.which("caffeinate") if sys.platform == "darwin" else None
        if tool is None or self._proc is not None:
            return
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [tool, "-i", "-m", "-w", str(os.getpid())], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            log.warning("could not start caffeinate: %s", e)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            with contextlib.suppress(OSError):
                proc.terminate()


class _Progress:
    """What ``transcribe.local`` calls: ``progress(fraction)`` and ``.cancelled``."""

    def __init__(self, cancel: threading.Event, report: Callable[[float], None]):
        self._cancel, self._report = cancel, report

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def __call__(self, value: float, *_rest, **_kw) -> None:
        self._report(value)


def _error(exc: Exception) -> dict:
    if isinstance(exc, KuulasError):
        return {"key": exc.key, "params": exc.params,
                "text": str(t(exc.key, **exc.params))}
    params = {"error": f"{type(exc).__name__}: {exc}"}
    return {"key": "error.job.failed", "params": params,
            "text": str(t("error.job.failed", **params))}


def _write_result(folder: Path, job_id: str, media_id: str, found: dict,
                  language: str) -> None:
    write_json_atomic(bgjobs.result_file(folder, job_id, media_id),
                      bgjobs.words_to_file(found["words"], timing=found["timing"],
                                           language=found.get("language") or language,
                                           rejected=found.get("rejected", 0)))


def _stop_if_cancelled(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise JobCancelledError


def _run_engines(job: dict, folder: Path, status: _Status, cancel: threading.Event,
                 local: Callable | None, colab: Callable | None) -> None:
    """Run the chosen engine over the job's media and write the result files."""
    job_id, items = str(job["id"]), job["items"]
    language = job.get("language") or ""
    if job["backend"] == "colab":
        engine = colab or colab_transcribe.run

        def report(fraction, message="", indeterminate=False):
            status.line(message)
            status.update(progress=max(status.data["progress"], min(1.0, fraction)),
                          message=message, indeterminate=bool(indeterminate))

        params = {"model": job.get("model"), "language": job.get("language")}
        found = engine(items, params, job.get("settings") or {}, report, cancel)
        _stop_if_cancelled(cancel)
        for item in items:
            _write_result(folder, job_id, item["id"], found["results"][item["id"]],
                          language)
        return
    engine = local or transcribe.local
    for index, item in enumerate(items):
        def share(fraction, index=index, name=item["name"]):
            status.update(progress=max(status.data["progress"], min(
                1.0, (index + min(1.0, max(0.0, fraction))) / len(items))),
                indeterminate=False, message=f"[{index + 1}/{len(items)}] {name}")

        words = engine(item["path"], model=job.get("model") or "small",
                       language=job.get("language"), progress=_Progress(cancel, share),
                       cpu_threads=job.get("cpu_threads"))
        _stop_if_cancelled(cancel)
        # A local engine makes Whisper's own word times: the file says so; the editor
        # does not store a timing marker for it (as before WP79).
        _write_result(folder, job_id, item["id"], {"words": words, "timing": "whisper"},
                      language)


def run_job(job_path: Path | str, *, local: Callable | None = None,
            colab: Callable | None = None, status_interval: float = STATUS_INTERVAL_S,
            cancel: threading.Event | None = None, keep_awake=None) -> str:
    """Run the job to its end and return the final state (``completed``, ``failed``
    or ``cancelled``). ``local`` and ``colab`` replace the engines (tests)."""
    job_path = Path(job_path)
    job = bgjobs.read_json(job_path)
    if job is None:
        raise bgjobs.BackgroundJobError("error.transcribe.bad_job", path=str(job_path))
    folder, job_id = job_path.parent.parent, str(job["id"])
    cancel = cancel or threading.Event()
    status = _Status(bgjobs.status_file(folder, job_id), status_interval)
    stop_watch = threading.Event()

    def watch() -> None:
        while not stop_watch.wait(CANCEL_POLL_S):
            status.flush_due()
            if bgjobs.cancel_file(folder, job_id).exists():
                cancel.set()

    watcher = threading.Thread(target=watch, daemon=True, name="kuulas-cancel-watch")
    if keep_awake is not None:
        keep_awake.start()
    status.update(force=True, state="running")
    watcher.start()
    final, fields = "completed", {"progress": 1.0, "message": ""}
    try:
        if bgjobs.cancel_file(folder, job_id).exists():
            cancel.set()
        _stop_if_cancelled(cancel)
        _run_engines(job, folder, status, cancel, local, colab)
    except JobCancelledError:
        final, fields = "cancelled", {}
    except Exception as exc:
        log.exception("job %s failed", job_id)
        final, fields = "failed", {"error": _error(exc)}
    finally:
        stop_watch.set()
        if keep_awake is not None:
            keep_awake.stop()
    status.update(force=True, state=final, indeterminate=False,
                  finished=bgjobs.now_iso(), **fields)
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kuulas-worker")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run one transcription job file")
    run.add_argument("job_file")
    args = parser.parse_args(argv)
    cancel = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: cancel.set())
    with contextlib.suppress(AttributeError):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)  # closing a terminal is not cancel
    state = run_job(args.job_file, cancel=cancel, keep_awake=_KeepAwake())
    return 1 if state == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
