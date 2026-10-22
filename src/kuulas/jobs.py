"""Cooperative background work with progress, cancellation and isolated errors.

Jobs yield to playback (docs/PLAYBACK-PRIORITY.md): a job does not start while
the engine plays, and pauses at its next progress call or ``priority.checkpoint``
once playback starts. It stays listed as running, with ``paused`` set and the
message "Paused while playing", resumes where it was, and can be cancelled while
paused."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

from . import media, priority
from .messages import KuulasError, t

log = logging.getLogger("kuulas.jobs")

#: Raised by a job after it observes cooperative cancellation. The same class as
#: ``priority.CancelledError``, so a chunk loop's ``checkpoint`` cancels a job.
JobCancelledError = priority.CancelledError

#: Finished jobs (completed, failed, cancelled) listed at most; the oldest go first.
#: A dialog polls the job it started every 0.1-0.5 s until it ends, so it reads
#: its result long before 64 newer jobs could finish. Before this bound every job
#: of the session stayed, with its result and its closure (the project snapshot it
#: worked on), and ``list`` (the live channel's, 4 times a second, 30 while playing)
#: grew with them.
FINISHED_KEPT = 64

#: Fields of a job's entry that ``list`` does not show.
_PRIVATE = frozenset({"created", "started", "paused_s", "paused_at", "own_message"})


def _cancelled() -> None:
    raise JobCancelledError


@dataclass
class _Progress:
    jobs: Jobs
    job_id: str
    cancelled_event: threading.Event

    @property
    def cancelled(self) -> bool:
        return self.cancelled_event.is_set()

    def __call__(self, value: float, message: str | None = None,
                 indeterminate: bool = False) -> None:
        """``value`` 0..1. ``message`` (a line to show beside the bar) and
        ``indeterminate`` (the bar cannot say how far it is) are for work whose
        progress is not a number, e.g. a child process that prints lines.
        While audio plays, this is where the job waits."""
        self.jobs._checkpoint(self.job_id, value, self.cancelled_event,
                              message, indeterminate)

    def set_eta(self, parts: list | None) -> None:
        """The time left as ``["minutes", 12]`` (``eta.remaining_parts``, JSON-friendly)
        or None; listed as the job's ``eta``."""
        self.jobs._set_eta(self.job_id, parts)

    def set_detail(self, detail: dict | None) -> None:
        """What the job is doing, as plain data for a structured toast (the automixer:
        ``{"phase", "phases", "phase_name", "track", "stage"}``, docs/design/TOAST.md),
        or None; listed as the job's ``detail``. ``message`` stays the text fallback."""
        self.jobs._set_detail(self.job_id, detail)


@dataclass
class _Work:
    fn: Callable
    on_done: Callable[[Any], None] | None
    keep_result: bool = False
    cancel: threading.Event = field(default_factory=threading.Event)
    future: Future | None = None


class Jobs:
    """Run independent tasks on a bounded worker pool and retain their status."""

    def __init__(self, max_workers: int | None = None,
                 gate: priority.PlaybackGate | None = None):
        self.max_workers = max_workers or media.workers()
        #: None: the process-wide ``priority.GATE``, looked up at each use (a test
        #: that replaces it is followed).
        self._playback = gate
        self._pool = priority.executor(self.max_workers, "kuulas-job")
        self._lock = threading.RLock()
        self._gate = threading.Condition(self._lock)
        self._active = 0
        self._interactive = False
        self._items: dict[str, dict] = {}
        self._work: dict[str, _Work] = {}
        #: Finished job ids, oldest end first (``_finished``).
        self._done: OrderedDict[str, None] = OrderedDict()
        self._closed = False

    def submit(self, kind: str, title: str,
               fn: Callable[[Callable[[float], None]], Any],
               on_done: Callable[[Any], None] | None = None,
               *, keep_result: bool = False) -> str:
        """Queue ``fn``. ``keep_result``: the value it returns (JSON-able) is
        listed with the finished job as ``result``, for a UI that has to show it."""
        job_id = uuid.uuid4().hex
        work = _Work(fn, on_done, keep_result)
        with self._lock:
            if self._closed:
                raise KuulasError("error.jobs.closed")
            self._items[job_id] = {"id": job_id, "kind": kind, "title": title,
                                   "progress": 0.0, "state": "queued", "error": None,
                                   "message": "", "indeterminate": False,
                                   "remaining_seconds": None, "eta": None,
                                   "detail": None,
                                   "created": time.monotonic(),
                                   "started": None, "paused": False, "paused_s": 0.0,
                                   "paused_at": None, "own_message": ""}
            self._work[job_id] = work
            work.future = self._pool.submit(self._run, job_id, work)
        return job_id

    def _run(self, job_id: str, work: _Work) -> None:
        with self._lock:
            item = self._items[job_id]
            if work.cancel.is_set():
                item["state"] = "cancelled"
                self._finished(job_id)
                return
            item["state"], item["started"] = "running", time.monotonic()
        priority.lower_this_thread()  # a job thread is background work, always
        progress = _Progress(self, job_id, work.cancel)
        entered = False
        try:
            # Background: every ``priority.checkpoint`` under this job (analysis
            # chunks, export blocks) pauses it while audio plays, and says so.
            with priority.background(work.cancel), priority.listening(
                    lambda: self._pause(job_id), lambda: self._resume(job_id)):
                self._enter(work.cancel)
                entered = True
                value = work.fn(progress)
            if work.cancel.is_set():
                _cancelled()
            if work.on_done is not None:
                work.on_done(value)
            with self._lock:
                item = self._items[job_id]
                item.update(state="completed", progress=1.0, remaining_seconds=0,
                            eta=None, detail=None, indeterminate=False, paused=False)
                if work.keep_result:
                    item["result"] = value
        except JobCancelledError:
            with self._lock:
                self._items[job_id].update(state="cancelled", remaining_seconds=None,
                                           eta=None, detail=None, paused=False)
        except Exception as exc:
            if isinstance(exc, KuulasError):
                log.exception("Background job %s failed: %s", job_id, exc.key)
                error = {"key": exc.key, "params": exc.params,
                         "text": str(t(exc.key, **exc.params))}
            else:
                log.exception("Background job %s failed", job_id)
                params = {"error": f"{type(exc).__name__}: {exc}"}
                error = {"key": "error.job.failed", "params": params,
                         "text": str(t("error.job.failed", **params))}
            with self._lock:
                self._items[job_id].update(state="failed", error=error,
                                           remaining_seconds=None, eta=None,
                                           detail=None, paused=False)
        finally:
            with self._lock:
                self._finished(job_id)
            if entered:
                self._leave()

    def _finished(self, job_id: str) -> None:
        """``job_id`` has ended (caller holds the lock): let go of its work (the
        closure and what it captured) and drop the oldest finished beyond
        ``FINISHED_KEPT``, in the order they ended: an export that ends after many
        short previews is the newest. Queued and running jobs are never dropped."""
        self._work.pop(job_id, None)
        self._done[job_id] = None
        while len(self._done) > FINISHED_KEPT:
            old, _ = self._done.popitem(last=False)
            self._items.pop(old, None)

    def _playback_gate(self) -> priority.PlaybackGate:
        return self._playback or priority.GATE

    def _busy(self) -> bool:
        """One job at a time runs a chunk: while the live loop says the user is
        busy (``set_interactive``), or the gate does (playing, recent input)."""
        return self._interactive or self._playback_gate().interactive()

    def _enter(self, cancelled: threading.Event) -> None:
        """Wait until playback stops and it is this job's turn; then hold one of
        the turns. Raises ``JobCancelledError`` when cancelled meanwhile."""
        while True:
            priority.checkpoint(cancelled, gate=self._playback_gate())
            with self._gate:
                if not (self._busy() and self._active >= 1):
                    self._active += 1
                    return
                self._gate.wait(0.1)

    def _leave(self) -> None:
        with self._gate:
            self._active = max(0, self._active - 1)
            self._gate.notify_all()

    def _pause(self, job_id: str) -> None:
        with self._lock:
            item = self._items.get(job_id)
            if item is None or item["paused"]:
                return
            item.update(paused=True, paused_at=time.monotonic(),
                        own_message=item["message"],
                        message=str(t("job.paused_playing")))

    def _resume(self, job_id: str) -> None:
        with self._lock:
            item = self._items.get(job_id)
            if item is None or not item["paused"]:
                return
            since = item["paused_at"]
            item["paused_s"] += time.monotonic() - since if since is not None else 0.0
            item.update(paused=False, paused_at=None, message=item["own_message"])

    def _set_eta(self, job_id: str, parts: list | None) -> None:
        with self._lock:
            item = self._items.get(job_id)
            if item is not None:
                item["eta"] = parts

    def _set_detail(self, job_id: str, detail: dict | None) -> None:
        with self._lock:
            item = self._items.get(job_id)
            if item is not None:
                item["detail"] = detail

    def _checkpoint(self, job_id: str, value: float, cancelled: threading.Event,
                    message: str | None = None, indeterminate: bool = False) -> None:
        with self._gate:
            item = self._items.get(job_id)
            if item is not None:
                item["progress"] = max(item["progress"], min(1.0, max(0.0, value)))
                item["indeterminate"] = bool(indeterminate)
                if message is not None:
                    if item["paused"]:
                        item["own_message"] = message  # shown again on resume
                    else:
                        item["message"] = message
            if not self._busy():
                return
            # Give the turn up while the user is busy; ``_enter`` waits for
            # playback to stop and for a turn, and takes it back.
            self._active = max(0, self._active - 1)
            self._gate.notify_all()
        try:
            self._enter(cancelled)
        except JobCancelledError:
            with self._gate:
                self._active += 1  # ``_run`` gives it back in ``_leave``
            raise

    def set_interactive(self, active: bool) -> None:
        with self._gate:
            self._interactive = active
            self._gate.notify_all()

    def list(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            result = []
            for item in self._items.values():
                copy = {key: value for key, value in item.items() if key not in _PRIVATE}
                if item["paused"]:
                    copy["remaining_seconds"] = None  # no estimate while it waits
                elif item["state"] == "running" and item["started"] is not None:
                    elapsed = now - item["started"] - item["paused_s"]
                    progress = item["progress"]
                    copy["remaining_seconds"] = (
                        round(elapsed * (1 - progress) / progress)
                        if progress > 0 and not item["indeterminate"] else None)
                result.append(copy)
            return result

    def cancel(self, job_id: str) -> None:
        with self._lock:
            item = self._items.get(job_id)
            work = self._work.get(job_id)
            if item is None:
                return
            if item["state"] in {"completed", "failed", "cancelled"}:
                return
            work.cancel.set()
            if work.future is not None and work.future.cancel():
                item.update(state="cancelled", remaining_seconds=None)
                self._finished(job_id)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for job_id, work in self._work.items():
                work.cancel.set()
                if self._items[job_id]["state"] == "queued":
                    self._items[job_id].update(state="cancelled", remaining_seconds=None)
            self._gate.notify_all()
        self._pool.shutdown(wait=True, cancel_futures=True)
