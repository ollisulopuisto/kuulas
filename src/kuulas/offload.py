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

Fail soft, but never into the editor's memory: a store the worker cannot
reopen (a test's in-memory store) or a worker that cannot be STARTED is
measured in the editor, one analysis at a time, under the gate, and not when
the editor is already past its memory warning. A worker that started and then
died (exit code, signal, no result) is an error (``error.offload.crashed``)
with the manager's back-off, never an inline run (docs/MEMORY.md).
``MODE = "inline"`` (tests, ``KUULAS_ANALYSIS=inline``) never starts a process.

At most one worker process lives at a time (``WorkerManager``, ``MANAGER``).
v26.10.20.2 started one per call: the UI asks for loudness curves after every
edit (and aborts the older request, which the server never notices), each
worker was stopped while audio played, and ~35 stopped workers took the Mac's
memory (owner's btop, 2026-10-20). Now:

- calls queue for the one slot (a cap on the queue); a newer call for the same
  thing (``SUPERSEDE``: the loudness curves of one project) ends the older,
  waiting or running;
- background work does not start a worker while audio plays (it waits in the
  queue); one already running is stopped and always continued or killed;
- every worker is killed and reaped on cancel, error, timeout (``WALL_S`` of
  running time), project close (``cancel_owner``) and exit (``atexit``); a
  watchdog kills a worker whose waiting thread stopped looking at it;
- the worker is in its own process group, so if the editor dies while it is
  stopped the kernel continues and hangs it up; a running worker also exits
  when its parent is gone (``analysis_worker``); ``sweep_orphans`` at start
  kills what an earlier crash left anyway.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib
import itertools
import logging
import os
import pickle
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from . import analysis_progress, priority, rss, toolpath
from .messages import KuulasError, t
from .processes import pid_alive

log = logging.getLogger("kuulas.offload")

#: "process" (the app) or "inline" (tests; conftest sets it).
MODE = os.environ.get("KUULAS_ANALYSIS", "process")

#: What the worker may run: ``fn(project, store, *args, **kwargs)``, pure on
#: the snapshot. A name, so the task file never names code.
TASKS: dict[str, str] = {
    "silence_ranges": "kuulas.analysis:silence_ranges",
    "raw_silence_ranges": "kuulas.analysis:raw_silence_ranges",
    "preview_silence": "kuulas.analysis:preview_silence",
    "silence_track_levels": "kuulas.analysis:measure_silence_track",
    "silence_learn": "kuulas.silence_learn:calibrate_tracks",
    "speech_lanes": "kuulas.analysis:speech_lanes",
    "anyone_talking_intervals": "kuulas.analysis:anyone_talking_intervals",
    "duck_sidechain": "kuulas.analysis:duck_sidechain_measure",
    "project_curves": "kuulas.loudness_curve:project_curves",
    "music_level": "kuulas.music_level:measure",
    "block_level": "kuulas.block_level:measure",
}

#: Tasks where only the newest call per project matters: a newer one ends the
#: older (the UI has already given up on it).
SUPERSEDE = frozenset({"project_curves"})

#: How often the waiting editor thread looks at cancel and the gate.
POLL_S = 0.05
#: How often a running worker's progress file is read.
PROGRESS_POLL_S = 0.2
#: Calls that may wait for the one worker; more is an error, not a pile.
MAX_QUEUED = 16
#: Running time (stopped time not counted) after which a worker is killed.
WALL_S = 600.0
#: After a failure or timeout, the same key waits this long before its next
#: worker, doubling with each failure in a row up to ``BACKOFF_MAX_S``.
BACKOFF_S = 5.0
BACKOFF_MAX_S = 300.0
#: The worker's nice level. Not 19 with the Darwin background band: on a
#: loaded Mac that starved it and it never finished (owner's ps, 2026-10-20).
WORKER_NICE = 10
#: Set in the worker's environment when its stdin is a pipe from the editor:
#: the worker exits when that pipe closes.
PIPE_ENV = "KUULAS_PARENT_PIPE"
#: A worker whose waiting thread has not looked at it this long is killed.
ABANDON_S = 30.0
#: A worker still stopped this long after playback ended is continued.
STOP_GRACE_S = 5.0
#: How often the watchdog looks.
WATCH_S = 1.0


class WorkerFailedError(Exception):
    """The worker gave no answer (not an error of the analysis itself)."""


class WorkerStartError(WorkerFailedError):
    """The worker process could not be started (spawn ``OSError``, no python or
    bundle executable). The only failure that may be measured in the editor."""


class WorkerCrashedError(WorkerFailedError):
    """The worker started but gave no answer: it exited non-zero (a signal is
    a negative code), wrote no result, or the result could not be read. Never
    measured in the editor: that is the memory the worker kept out of it."""

    def __init__(self, detail: str, code: int | None = None):
        super().__init__(detail)
        self.code = code


class SupersededError(priority.CancelledError):
    """A newer call for the same thing replaced this one."""


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
         pause: bool | None = None,
         on_progress: Callable[[float, str, dict], None] | None = None,
         **kwargs: Any) -> Any:
    """``TASKS[task](project, store, *args, **kwargs)``, in the worker process.

    ``cancel`` (default: the calling job's) kills the worker and raises
    ``CancelledError``. ``pause`` (default: whether the caller is background
    work) stops the worker while audio plays. ``on_progress(fraction, stage,
    detail)`` hears what the task reports (``analysis_progress.report``), while it
    runs."""
    fn = resolve(task)
    spec = store_spec(store) if MODE == "process" else None
    if spec is None:
        analysis_progress.set_callback(on_progress)
        try:
            return fn(project, store, *args, **kwargs)
        finally:
            analysis_progress.set_callback(None)
    payload = {"task": task, "project": project, "store": spec, "args": args,
               "kwargs": kwargs}
    key = (task, spec["folder"]) if task in SUPERSEDE else None
    # A task that hit the memory ceiling backs off like a failed worker, even
    # when it is not superseding: no retry storm of workers that each grow to
    # the ceiling (docs/MEMORY.md).
    memory_key = ("memory", task, spec["folder"])
    left = MANAGER.backoff_left(memory_key)
    if left > 0:
        raise KuulasError("error.offload.backoff", seconds=round(left))
    crash_key = ("crash", task, spec["folder"])
    left = MANAGER.backoff_left(crash_key)
    if left > 0:
        raise KuulasError("error.offload.backoff", seconds=round(left))
    try:
        reply = _run(payload, cancel, pause, key=key, owner=spec["folder"],
                     on_progress=on_progress)
    except WorkerStartError as e:
        log.warning(t("log.offload.fallback", error=str(e)))
        return _run_inline(fn, task, cancel, project, store, args, kwargs, on_progress)
    except WorkerCrashedError as e:
        MANAGER.note_failure(crash_key)
        raise KuulasError("error.offload.crashed", exit=describe_exit(e.code),
                          detail=str(e)) from e
    note_worker_peak(task, reply.get("peak_rss"))
    error = reply.get("error")
    if error is not None:
        if error.get("key") == "error.offload.memory":
            MANAGER.note_failure(memory_key)
        raise _rebuild(error)
    MANAGER.note_success(memory_key)
    return reply["value"]


def describe_exit(code: int | None) -> str:
    """``exit 1``, or ``exit -9 (SIGKILL)`` for a death by signal."""
    if code is None:
        return "no result"
    if code < 0:
        try:
            return f"exit {code} ({signal.Signals(-code).name})"
        except ValueError:
            return f"exit {code}"
    return f"exit {code}"


def memory_kill_suspect(code: int | None) -> bool:
    """Killed by SIGKILL (-9, or 137/9 through a shell or launcher): what macOS
    does to a process when memory runs out (Jetsam), or the ceiling's last resort."""
    return code in (-9, 137, 9)


#: One inline analysis at a time, process-wide, and what the performance report
#: shows of it.
_INLINE_LOCK = threading.Lock()
INLINE: dict[str, Any] = {"runs": 0, "running": False}


def _run_inline(fn: Callable, task: str, cancel: threading.Event | None, project,
                store, args: tuple, kwargs: dict, on_progress=None) -> Any:
    """The fallback for a worker that could not be started: one at a time, under
    the playback gate, and not when the editor is already big (docs/MEMORY.md)."""
    from .memory import RSS_WARN_BYTES  # noqa: PLC0415 - memory imports caches

    while not _INLINE_LOCK.acquire(timeout=POLL_S):
        priority.checkpoint(cancel)
    try:
        now = rss.current()
        if now is not None and now > RSS_WARN_BYTES:
            raise KuulasError("error.offload.memory", mb=round(now / 1024**2),
                              limit_mb=round(RSS_WARN_BYTES / 1024**2))
        INLINE["runs"] += 1
        INLINE["running"] = True
        log.warning(t("log.offload.inline", task=task))
        priority.checkpoint(cancel)
        analysis_progress.set_callback(on_progress)
        return fn(project, store, *args, **kwargs)
    finally:
        analysis_progress.set_callback(None)
        INLINE["running"] = False
        _INLINE_LOCK.release()


#: The analysis workers' peak resident bytes: the last one's and the most any
#: reached in this run (the performance report, docs/MEMORY.md).
WORKER_PEAKS: dict[str, int] = {"last": 0, "max": 0}


def note_worker_peak(task: str, peak: object) -> None:
    if not isinstance(peak, int) or peak <= 0:
        return
    WORKER_PEAKS["last"] = peak
    WORKER_PEAKS["max"] = max(WORKER_PEAKS["max"], peak)
    log.info("analysis worker %s: peak RSS %d MB", task, round(peak / 1024**2))


def probe(what: dict, cancel: threading.Event | None = None,
          pause: bool | None = None, on_progress=None) -> dict:
    """Ask the worker about itself (``{"what": "priority"}``) or have it spin
    (``{"what": "spin", "seconds": s}``): the selftest and the tests."""
    reply = _run({"task": "_probe", "probe": what}, cancel, pause,
                 on_progress=on_progress)
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


def _kill(proc: subprocess.Popen) -> None:
    """Continue (a stopped process takes SIGKILL too, but say it) and kill."""
    _signal(proc, "SIGCONT")
    if proc.poll() is None:
        with contextlib.suppress(OSError):
            proc.kill()


def spawn_options() -> dict:
    """How a worker is started: no inherited files, and (POSIX) a process group
    of its own in the editor's session. When the editor dies, that group is
    orphaned, and the kernel sends SIGHUP and SIGCONT to a stopped member, so a
    worker stopped for playback does not outlive the editor."""
    options: dict = {"stdin": subprocess.PIPE, "stdout": subprocess.DEVNULL,
                     "close_fds": True}
    if os.name == "posix":
        options["process_group"] = 0
    return options


class _Request:
    """One call waiting for, or using, the worker slot."""

    def __init__(self, seq: int, key: object, owner: str | None, pause: bool,
                 cancel: threading.Event | None):
        self.seq, self.key, self.owner = seq, key, owner
        self.pause, self.cancel = pause, cancel
        self.proc: subprocess.Popen | None = None
        self.stopped = False
        self.quiet_since: float | None = None  # stopped, but the gate is quiet
        self.last_poll = time.monotonic()
        #: Why it ends early: superseded, preempted, cancelled, closed, abandoned.
        self.ended: str | None = None

    def error(self) -> BaseException:
        if self.ended == "superseded":
            return SupersededError()
        return priority.CancelledError()


class WorkerManager:
    """At most one analysis worker process at a time (see the module doc)."""

    def __init__(self, *, max_queued: int = MAX_QUEUED, wall_s: float = WALL_S,
                 abandon_s: float = ABANDON_S, stop_grace_s: float = STOP_GRACE_S,
                 watch_s: float = WATCH_S, poll_s: float = POLL_S,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic):
        self.max_queued, self.wall_s, self.abandon_s = max_queued, wall_s, abandon_s
        self.stop_grace_s, self.watch_s, self.poll_s = stop_grace_s, watch_s, poll_s
        self._popen = popen
        self._clock = clock
        #: key -> (failures in a row, no new worker before this clock time)
        self._failures: dict[object, tuple[int, float]] = {}
        self._cond = threading.Condition()
        self._waiting: list[_Request] = []
        self._running: _Request | None = None
        self._seq = itertools.count()
        self._closed = False
        self._watchdog: threading.Thread | None = None

    # -- what the editor calls ------------------------------------------------

    def run(self, argv: list[str], *, key: object = None, owner: str | None = None,
            cancel: threading.Event | None = None, pause: bool = False,
            on_pause: Callable[[], None] | None = None,
            on_resume: Callable[[], None] | None = None,
            stderr: Any = None, env: dict | None = None) -> int:
        """Run ``argv`` as the worker when its turn comes; its exit code.

        ``key``: a newer call with the same key ends this one
        (``SupersededError``). ``owner``: ``cancel_owner`` ends it. ``pause``:
        background work, which does not start while audio plays and is stopped
        while it plays. Raises ``CancelledError`` on cancel or shutdown, and
        ``KuulasError`` when the queue is full, the worker runs too long, or
        ``key`` failed lately (``backoff_left``; no worker is started then)."""
        req = _Request(next(self._seq), key, owner, pause, cancel)
        with self._cond:
            if self._closed:
                raise priority.CancelledError
            left = self._backoff_left(key)
            if left > 0:
                raise KuulasError("error.offload.backoff", seconds=round(left))
            if key is not None:
                for other in [*self._waiting, self._running]:
                    if other is not None and other.key == key and other.ended is None:
                        self._end(other, "superseded")
            if len(self._waiting) >= self.max_queued:
                raise KuulasError("error.offload.busy")
            self._waiting.append(req)
            self._cond.notify_all()
        self._ensure_watchdog()
        while True:
            self._take_slot(req)
            try:
                code = self._attend(req, argv, on_pause, on_resume, stderr, env)
            except (KuulasError, WorkerFailedError):
                self._failed(key)
                raise
            finally:
                self._release(req)
            if code is not None:
                if code == 0:
                    self._succeeded(key)
                else:
                    self._failed(key)
            if code is None:  # preempted by a foreground call: wait again
                with self._cond:
                    req.ended = None
                    self._waiting.insert(0, req)
                    self._cond.notify_all()
                continue
            return code

    def cancel_owner(self, owner: str) -> None:
        """End every call of ``owner`` (a project being closed)."""
        with self._cond:
            for req in [*self._waiting, self._running]:
                if req is not None and req.owner == owner and req.ended is None:
                    self._end(req, "cancelled")

    def shutdown(self, timeout: float = 2.0) -> None:
        """End every call and kill the worker (interpreter exit); later calls
        raise ``CancelledError``."""
        with self._cond:
            self._closed = True
            for req in [*self._waiting, self._running]:
                if req is not None and req.ended is None:
                    self._end(req, "closed")
            proc = self._running.proc if self._running is not None else None
        if proc is not None:
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                proc.wait(timeout)

    def backoff_left(self, key: object) -> float:
        """Seconds before ``key`` may start a worker again (0: now)."""
        with self._cond:
            return self._backoff_left(key)

    def _backoff_left(self, key: object) -> float:
        if key is None or key not in self._failures:
            return 0.0
        return max(0.0, self._failures[key][1] - self._clock())

    def note_failure(self, key: object) -> None:
        """A failure of ``key`` the worker reported in its answer (the memory
        ceiling): back off as after a crash."""
        self._failed(key)

    def note_success(self, key: object) -> None:
        if key in self._failures:
            self._succeeded(key)

    def _failed(self, key: object) -> None:
        if key is None:
            return
        with self._cond:
            count = self._failures.get(key, (0, 0.0))[0] + 1
            wait = min(BACKOFF_S * 2 ** (count - 1), BACKOFF_MAX_S)
            self._failures[key] = (count, self._clock() + wait)

    def _succeeded(self, key: object) -> None:
        with self._cond:
            self._failures.pop(key, None)

    def alive(self) -> list[int]:
        """The pid of the worker process, when one runs."""
        with self._cond:
            r = self._running
            return [r.proc.pid] if r is not None and r.proc is not None \
                and r.proc.poll() is None else []

    # -- inside ---------------------------------------------------------------

    def _end(self, req: _Request, why: str) -> None:
        """Under the lock: ``req`` ends; a waiting one leaves the queue, a running
        one's worker is killed (its own thread reaps it)."""
        req.ended = why
        if req in self._waiting:
            self._waiting.remove(req)
        if req.proc is not None:
            _kill(req.proc)
        self._cond.notify_all()

    def _next(self) -> _Request | None:
        """Whose turn it is: foreground calls first, then the oldest; background
        work does not start while audio plays."""
        playing = priority.GATE.is_playing()
        ready = [r for r in self._waiting if not (r.pause and playing)]
        return min(ready, key=lambda r: (r.pause, r.seq)) if ready else None

    def _take_slot(self, req: _Request) -> None:
        with self._cond:
            while True:
                if req.ended is not None:
                    raise req.error()
                if self._closed:
                    self._end(req, "closed")
                    raise req.error()
                if req.cancel is not None and req.cancel.is_set():
                    self._end(req, "cancelled")
                    raise req.error()
                if self._running is None and self._next() is req:
                    self._waiting.remove(req)
                    self._running = req
                    req.last_poll = time.monotonic()
                    return
                running = self._running
                if (running is not None and not req.pause and running.pause
                        and running.stopped and running.ended is None):
                    # A user's command does not wait for playback to end behind
                    # stopped background work: that work starts again later.
                    self._end(running, "preempted")
                self._cond.wait(self.poll_s)

    def _release(self, req: _Request) -> None:
        with self._cond:
            if self._running is req:
                self._running = None
            req.proc = None
            self._cond.notify_all()

    def _attend(self, req: _Request, argv: list[str], on_pause, on_resume, stderr,
                env) -> int | None:
        """Start the worker and wait for it; None when it was preempted."""
        options = spawn_options()
        if stderr is not None:
            options["stderr"] = stderr
        env = {**(os.environ if env is None else env), PIPE_ENV: "1"}
        try:
            proc = self._popen(argv, env=env, **options)
        except OSError as e:
            raise WorkerStartError(str(e)) from e
        try:
            with self._cond:
                req.proc = proc
                if req.ended is not None:
                    _kill(proc)
            ran, last = 0.0, time.monotonic()
            while True:
                try:
                    code = proc.wait(timeout=self.poll_s)
                    break
                except subprocess.TimeoutExpired:
                    pass
                now = time.monotonic()
                req.last_poll = now
                if not req.stopped:
                    ran += now - last
                last = now
                if req.ended is not None:
                    break
                if req.cancel is not None and req.cancel.is_set():
                    raise priority.CancelledError
                if ran > self.wall_s:
                    raise KuulasError("error.offload.timeout", seconds=round(self.wall_s))
                # Background work: frozen while the editor plays.
                want = req.pause and priority.GATE.is_playing()
                if want != req.stopped:
                    _signal(proc, "SIGSTOP" if want else "SIGCONT")
                    req.stopped = want
                    hook = on_pause if want else on_resume
                    if hook is not None:
                        hook()
            if req.ended == "preempted":
                return None
            if req.ended is not None:
                raise req.error()
            return code
        finally:
            was_stopped, req.stopped = req.stopped, False
            _kill(proc)
            with contextlib.suppress(OSError):
                proc.wait()
            if proc.stdin is not None:
                with contextlib.suppress(OSError):
                    proc.stdin.close()
            if was_stopped and on_resume is not None:
                on_resume()

    # -- the watchdog -----------------------------------------------------------

    def _ensure_watchdog(self) -> None:
        with self._cond:
            if self._watchdog is not None and self._watchdog.is_alive():
                return
            self._watchdog = priority.thread(self._watch, "kuulas-offload-watchdog")
            self._watchdog.start()

    def _watch(self) -> None:
        while True:
            with self._cond:
                if self._closed and self._running is None:
                    return
                self._watch_once(time.monotonic())
            time.sleep(self.watch_s)

    def _watch_once(self, now: float) -> None:
        """Under the lock: kill a worker its thread no longer looks after, and
        continue one still stopped well after playback ended."""
        req = self._running
        proc = req.proc if req is not None else None
        if req is None or proc is None or proc.poll() is not None:
            return
        if now - req.last_poll > self.abandon_s:
            log.warning(t("log.offload.watchdog", pid=proc.pid,
                          why=f"not looked after for {now - req.last_poll:.0f} s"))
            req.ended = "abandoned"
            _kill(proc)
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                proc.wait(1.0)
            # The slot is free: the stuck thread finds its worker gone.
            self._running = None
            self._cond.notify_all()
            return
        if req.stopped and not priority.GATE.is_playing():
            req.quiet_since = req.quiet_since if req.quiet_since is not None else now
            if now - req.quiet_since > self.stop_grace_s:
                log.warning(t("log.offload.watchdog", pid=proc.pid,
                              why="still stopped after playback"))
                _signal(proc, "SIGCONT")
                req.stopped = False
        else:
            req.quiet_since = None


#: The editor's one manager; ``atexit`` kills its worker.
MANAGER = WorkerManager()


@atexit.register
def _shutdown() -> None:
    MANAGER.shutdown()
    if _CENSUS_AT_EXIT:
        with contextlib.suppress(Exception):
            log_children("exit")


#: The editor (``start_sweep``) asks for a census at exit too; tests do not.
_CENSUS_AT_EXIT = False


def _watch_progress(path: Path, on_progress) -> Callable[[], None]:
    """Read the worker's progress file while it runs and pass each new report on; returns
    the function that stops watching (after one last look)."""
    stop = threading.Event()
    last: list = [None]

    def look() -> None:
        found = analysis_progress.read(path)
        if found is not None and found != last[0]:
            last[0] = found
            with contextlib.suppress(Exception):
                on_progress(*found)

    def loop() -> None:
        while not stop.wait(PROGRESS_POLL_S):
            look()

    thread = threading.Thread(target=loop, name="kuulas-progress", daemon=True)
    thread.start()

    def finish() -> None:
        stop.set()
        thread.join(timeout=2)
        look()

    return finish


def _run(payload: dict, cancel: threading.Event | None, pause: bool | None, *,
         key: object = None, owner: str | None = None, on_progress=None) -> dict:
    cancel = cancel if cancel is not None else priority._cancel()
    pause = priority.is_background() if pause is None else pause
    on_pause, on_resume = priority._listener() or (None, None)
    with tempfile.TemporaryDirectory(prefix="kuulas-analysis-") as tmp:
        task, result, errors = (Path(tmp) / n for n in ("task.pickle", "result.pickle",
                                                         "stderr.txt"))
        task.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
        env = toolpath.tool_env()
        listener = None
        if on_progress is not None:
            progress_file = Path(tmp) / "progress.json"
            env[analysis_progress.PROGRESS_ENV] = str(progress_file)
            listener = _watch_progress(progress_file, on_progress)
        try:
            with errors.open("wb") as err:
                code = MANAGER.run(worker_argv(task, result), key=key, owner=owner,
                                   cancel=cancel, pause=pause, on_pause=on_pause,
                                   on_resume=on_resume, stderr=err, env=env)
        finally:
            if listener is not None:
                listener()
        if code != 0 or not result.exists():
            tail = errors.read_bytes()[-400:].decode("utf-8", "replace").strip()
            detail = f"exit {code}: {tail}" if tail else f"exit {code}"
            if memory_kill_suspect(code):
                log.warning(t("log.offload.killed", code=describe_exit(code)))
            raise WorkerCrashedError(detail, code)
        try:
            return pickle.loads(result.read_bytes())  # noqa: S301 - our own child wrote it
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError) as e:
            raise WorkerCrashedError(str(e), code) from e


# -- workers an earlier run left behind ------------------------------------------

#: ``-m kuulas.analysis_worker`` as its own words in a command line (the bundle's
#: launcher and ``python`` alike). Never the transcription worker, which is
#: detached on purpose.
_WORKER_COMMAND = re.compile(r"(?:^|\s)-m\s+kuulas\.analysis_worker(?:\s|$)")


def _pid_alive(pid: int) -> bool:
    return pid_alive(pid) is not False


def sweep_orphans(*, listing: str | None = None,
                  kill: Callable[[int, int], None] = os.kill,
                  alive: Callable[[int], bool] = _pid_alive) -> list[int]:
    """Kill this user's analysis workers whose editor is gone (parent pid 1 or
    no longer there): what a crash of an earlier run left, stopped or not.
    Nothing else is touched. The pids killed; never raises."""
    if os.name != "posix":
        return []
    listing = _ps() if listing is None else listing
    me, uid = os.getpid(), os.getuid()
    killed = []
    for pid, ppid, owner, command in _rows(listing):
        if owner != uid or pid == me or not _WORKER_COMMAND.search(command):
            continue
        if ppid != 1 and alive(ppid):
            continue
        for sig in (signal.SIGCONT, signal.SIGKILL):
            with contextlib.suppress(OSError):
                kill(pid, sig)
        killed.append(pid)
    if killed:
        log.warning(t("log.offload.swept", count=len(killed)))
    return killed


def _ps() -> str:
    """``pid ppid uid command`` of every process; empty when ps fails."""
    try:
        return subprocess.run(["ps", "-ax", "-o", "pid=,ppid=,uid=,command="],  # noqa: S607 - the system's ps
                              capture_output=True, text=True, check=True,
                              timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _rows(listing: str) -> Iterator[tuple[int, int, int, str]]:
    for line in listing.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            yield int(parts[0]), int(parts[1]), int(parts[2]), parts[3]
        except ValueError:
            continue


_MODULE = re.compile(r"(?:^|\s)-m\s+(\S+)")


def module_of(command: str) -> str:
    """``kuulas.analysis_worker`` for ``.../Kuulas -m kuulas.analysis_worker ...``,
    else the program's name (``ffmpeg``): what btop's truncated line hides."""
    found = _MODULE.search(command)
    if found:
        return found.group(1)
    return Path(command.split(None, 1)[0]).name if command.strip() else "?"


def child_modules(listing: str | None = None, parent: int | None = None) -> dict:
    """``{module or program: count}`` of the live children of ``parent``
    (default: this process)."""
    listing = _ps() if listing is None else listing
    parent = os.getpid() if parent is None else parent
    out: dict[str, int] = {}
    for _pid, ppid, _uid, command in _rows(listing):
        if ppid == parent:
            name = module_of(command)
            out[name] = out.get(name, 0) + 1
    return out


def orphan_modules(listing: str | None = None, uid: int | None = None) -> dict:
    """``{module: count}`` of this user's ``-m kuulas...`` processes whose parent
    is gone (parent pid 1): what a crash or a leak left behind."""
    listing = _ps() if listing is None else listing
    uid = os.getuid() if uid is None else uid
    out: dict[str, int] = {}
    for _pid, ppid, owner, command in _rows(listing):
        name = module_of(command)
        if owner == uid and ppid == 1 and name.startswith("kuulas"):
            out[name] = out.get(name, 0) + 1
    return out


def log_children(when: str) -> None:
    """One log line: this editor's child processes and the left-behind kuulas
    processes, by module, so a future leak can be named from kuulas.log."""
    if os.name != "posix":
        return
    listing = _ps()
    log.info("processes at %s: children %s, left behind %s, analysis worker %s",
             when, child_modules(listing) or "none", orphan_modules(listing) or "none",
             MANAGER.alive() or "none")


def start_sweep() -> None:
    """At the editor's start, on a background thread: log what is there, then
    ``sweep_orphans``."""
    global _CENSUS_AT_EXIT  # noqa: PLW0603 - set once at the editor's start
    _CENSUS_AT_EXIT = True

    def run() -> None:
        log_children("start")
        sweep_orphans()

    priority.thread(run, "kuulas-offload-sweep").start()
