"""Cooperative background work with progress, cancellation and isolated errors."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from . import media
from .messages import KuulasError, t

log = logging.getLogger("kuulas.jobs")


class JobCancelledError(Exception):
    """Raised by a job after it observes cooperative cancellation."""


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

    def __call__(self, value: float) -> None:
        self.jobs._checkpoint(self.job_id, value, self.cancelled_event)


@dataclass
class _Work:
    fn: Callable
    on_done: Callable[[Any], None] | None
    keep_result: bool = False
    cancel: threading.Event = field(default_factory=threading.Event)
    future: Future | None = None


class Jobs:
    """Run independent tasks on a bounded worker pool and retain their status."""

    def __init__(self, max_workers: int | None = None):
        self.max_workers = max_workers or media.workers()
        self._pool = ThreadPoolExecutor(max_workers=self.max_workers,
                                         thread_name_prefix="kuulas-job")
        self._lock = threading.RLock()
        self._gate = threading.Condition(self._lock)
        self._active = 0
        self._interactive = False
        self._items: dict[str, dict] = {}
        self._work: dict[str, _Work] = {}
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
                                   "remaining_seconds": None, "created": time.monotonic(),
                                   "started": None}
            self._work[job_id] = work
            work.future = self._pool.submit(self._run, job_id, work)
        return job_id

    def _run(self, job_id: str, work: _Work) -> None:
        with self._lock:
            item = self._items[job_id]
            if work.cancel.is_set():
                item["state"] = "cancelled"
                return
            item["state"], item["started"] = "running", time.monotonic()
        progress = _Progress(self, job_id, work.cancel)
        entered = False
        try:
            entered = self._enter(work.cancel)
            if not entered:
                _cancelled()
            value = work.fn(progress)
            if work.cancel.is_set():
                _cancelled()
            if work.on_done is not None:
                work.on_done(value)
            with self._lock:
                item = self._items[job_id]
                item.update(state="completed", progress=1.0, remaining_seconds=0)
                if work.keep_result:
                    item["result"] = value
        except JobCancelledError:
            with self._lock:
                self._items[job_id].update(state="cancelled", remaining_seconds=None)
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
                                           remaining_seconds=None)
        finally:
            if entered:
                self._leave()

    def _enter(self, cancelled: threading.Event) -> bool:
        with self._gate:
            while self._interactive and self._active >= 1 and not cancelled.is_set():
                self._gate.wait(0.1)
            if cancelled.is_set():
                return False
            self._active += 1
            return True

    def _leave(self) -> None:
        with self._gate:
            self._active = max(0, self._active - 1)
            self._gate.notify_all()

    def _checkpoint(self, job_id: str, value: float,
                    cancelled: threading.Event) -> None:
        with self._gate:
            item = self._items.get(job_id)
            if item is not None:
                item["progress"] = max(item["progress"], min(1.0, max(0.0, value)))
            if not self._interactive:
                return
            self._active = max(0, self._active - 1)
            self._gate.notify_all()
            while self._interactive and self._active >= 1 and not cancelled.is_set():
                self._gate.wait(0.1)
            self._active += 1

    def set_interactive(self, active: bool) -> None:
        with self._gate:
            self._interactive = active
            self._gate.notify_all()

    def list(self) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            result = []
            for item in self._items.values():
                copy = {key: value for key, value in item.items()
                        if key not in {"created", "started"}}
                if item["state"] == "running" and item["started"] is not None:
                    elapsed = now - item["started"]
                    progress = item["progress"]
                    copy["remaining_seconds"] = (
                        round(elapsed * (1 - progress) / progress)
                        if progress > 0 else None)
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

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for job_id, work in self._work.items():
                work.cancel.set()
                if self._items[job_id]["state"] == "queued":
                    self._items[job_id].update(state="cancelled", remaining_seconds=None)
            self._gate.notify_all()
        self._pool.shutdown(wait=True, cancel_futures=True)
