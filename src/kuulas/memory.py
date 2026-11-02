"""One memory budget for every in-memory cache (PLAN ground rule 15).

Peak pyramids, level envelopes, decoded history states and memoized views
all live in one LRU, so their total can never pass ``limit`` (default 2 GB;
``configure`` or ``set_limit`` change it). When something is pushed out, a
numpy array that has a ``spill`` file is written there first (``caches/``,
docs/FORMAT.md) and read back on the next miss; anything else is simply
dropped, because every cache entry can be computed again.

Hit rates are counted per namespace and logged (``log_stats``), so a slow
edit can be traced to a cache that is not hitting.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from . import caches
from .messages import t

log = logging.getLogger("kuulas.memory")

#: Total size of everything cached in memory.
DEFAULT_LIMIT = 2 * 1024**3
#: Log the hit rates after this many lookups, so a long session reports itself.
LOG_EVERY = 5000
#: Caps of single namespaces inside the budget. ``chunks`` is decoded audio
#: (``MediaStore._chunk``, 10 s each): without its own cap every scan of a
#: long project filled the whole 2 GB with audio, in the editor and in each
#: analysis worker (47 min x 5 tracks: 2.4 to 3.4 GB peak RSS per process,
#: docs/MEMORY.md). Playback reads ahead through the engine's own window
#: (``engine.PREFETCH_S``), so this cache only spares repeated short reads:
#: 192 MB is ~17 minutes of mono audio at 48 kHz.
NAMESPACE_LIMITS = {"chunks": 192 * 1024**2}


def _sizeof(value: Any) -> int:
    """Bytes of an array, or of a dict of arrays; anything else needs ``nbytes``."""
    if isinstance(value, dict):
        return sum(_sizeof(v) for v in value.values())
    return int(value.nbytes)


class _Entry:
    __slots__ = ("nbytes", "spill", "value")

    def __init__(self, value: Any, nbytes: int, spill: Path | None):
        self.value, self.nbytes, self.spill = value, nbytes, spill


class _Computation:
    """One gate shared by its current runner and every registered waiter."""

    __slots__ = ("lock", "users")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.users = 0


class MemoryBudget:
    def __init__(self, limit_bytes: int = DEFAULT_LIMIT):
        self.limit = int(limit_bytes)
        self.used = 0
        self._entries: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self._lock = threading.RLock()
        #: One lock per key being computed, so two threads wanting the same
        #: envelope compute it once (a speech lane per core asks together).
        self._computing: dict[tuple[str, str], _Computation] = {}
        self._counts: dict[str, dict[str, int]] = {}
        self._lookups = 0
        self._ns_limits: dict[str, int] = dict(NAMESPACE_LIMITS)
        self._ns_used: dict[str, int] = {}

    # -- namespaces ---------------------------------------------------------

    def set_namespace_limit(self, ns: str, limit_bytes: int | None) -> None:
        """Cap ``ns`` on its own (None: only the total applies)."""
        with self._lock:
            if limit_bytes is None:
                self._ns_limits.pop(ns, None)
            else:
                self._ns_limits[ns] = int(limit_bytes)
            self._evict()

    def namespace_limit(self, ns: str) -> int | None:
        return self._ns_limits.get(ns)

    def namespace_bytes(self, ns: str) -> int:
        with self._lock:
            return self._ns_used.get(ns, 0)

    def namespace_usage(self) -> dict[str, int]:
        """``{namespace: bytes held}`` (the performance report)."""
        with self._lock:
            return {ns: n for ns, n in self._ns_used.items() if n}

    def _add(self, ns: str, nbytes: int) -> None:
        self.used += nbytes
        self._ns_used[ns] = self._ns_used.get(ns, 0) + nbytes

    # -- counting -----------------------------------------------------------

    def _count(self, ns: str, what: str) -> None:
        c = self._counts.setdefault(ns, {"hits": 0, "disk_hits": 0, "misses": 0})
        c[what] += 1
        self._lookups += 1
        if self._lookups % LOG_EVERY == 0:
            self.log_stats()

    def stats(self) -> dict[str, dict[str, float]]:
        with self._lock:
            out = {}
            for ns, c in self._counts.items():
                total = c["hits"] + c["disk_hits"] + c["misses"]
                out[ns] = {**c, "hit_rate": (c["hits"] + c["disk_hits"]) / total
                           if total else 0.0}
            return out

    def log_stats(self) -> None:
        for ns, s in self.stats().items():
            log.info(t("log.cache.stats", kind=ns, hits=s["hits"],
                       disk_hits=s["disk_hits"], misses=s["misses"],
                       rate=round(100 * s["hit_rate"]),
                       used_mb=round(self.used / 1024**2), limit_mb=round(
                           self.limit / 1024**2)))

    # -- the cache ----------------------------------------------------------

    def get(self, ns: str, key: str, *, spill: Path | None = None) -> Any | None:
        """The cached value, from memory, else from its ``spill`` file; else None."""
        with self._lock:
            entry = self._entries.get((ns, key))
            if entry is not None:
                self._entries.move_to_end((ns, key))
                self._count(ns, "hits")
                return entry.value
        if spill is not None:
            try:
                value = np.load(spill)
            except (OSError, ValueError, EOFError):
                value = None  # never written, deleted, or damaged: recompute
            if value is not None:
                self.put(ns, key, value, spill=spill)
                with self._lock:
                    self._count(ns, "disk_hits")
                return value
        with self._lock:
            self._count(ns, "misses")
        return None

    def put(self, ns: str, key: str, value: Any, nbytes: int | None = None, *,
            spill: Path | None = None) -> None:
        """Keep ``value``. ``nbytes`` is needed for anything but an ndarray.
        An entry bigger than the whole budget is not kept (but is spilled)."""
        size = _sizeof(value) if nbytes is None else int(nbytes)
        with self._lock:
            old = self._entries.pop((ns, key), None)
            if old is not None:
                self._add(ns, -old.nbytes)
            if size > min(self.limit, self._ns_limits.get(ns, self.limit)):
                self._spill(_Entry(value, size, spill))
                return
            self._entries[ns, key] = _Entry(value, size, spill)
            self._add(ns, size)
            self._evict()

    def discard(self, ns: str, key: str) -> None:
        with self._lock:
            entry = self._entries.pop((ns, key), None)
            if entry is not None:
                self._add(ns, -entry.nbytes)

    def discard_prefix(self, ns: str, prefix: str) -> None:
        """Discard all entries in ``ns`` whose key starts with ``prefix``."""
        with self._lock:
            to_remove = [k for k in self._entries
                         if k[0] == ns and k[1].startswith(prefix)]
            for k in to_remove:
                entry = self._entries.pop(k, None)
                if entry is not None:
                    self._add(ns, -entry.nbytes)

    def set_limit(self, limit_bytes: int) -> None:
        with self._lock:
            self.limit = int(limit_bytes)
            self._evict()

    def _evict(self) -> None:
        while self.used > self.limit and self._entries:
            (ns, _), entry = self._entries.popitem(last=False)
            self._add(ns, -entry.nbytes)
            self._spill(entry)
        for ns, cap in self._ns_limits.items():
            if self._ns_used.get(ns, 0) <= cap:
                continue
            for k in [k for k in self._entries if k[0] == ns]:  # oldest first
                if self._ns_used.get(ns, 0) <= cap:
                    break
                entry = self._entries.pop(k)
                self._add(ns, -entry.nbytes)
                self._spill(entry)

    @staticmethod
    def _spill(entry: _Entry) -> None:
        if entry.spill is None or not isinstance(entry.value, np.ndarray):
            return
        if entry.spill.exists():
            return
        try:
            caches.write_atomic(entry.spill, lambda f: np.save(f, entry.value))
        except OSError:
            # A full or read-only disk costs the spill, not the session: the
            # entry can be computed again.
            log.warning(t("log.cache.spill_failed", path=str(entry.spill)))

    def fetch(self, ns: str, key: str, compute: Callable[[], Any], *,
              nbytes: int | None = None, spill: Path | None = None) -> Any:
        """The cached value, or ``compute()`` it once and keep it.

        With ``spill``, a computed array is also written there at once, so
        the next process finds it: that file is the persistent cache entry
        (``caches/``), memory only a faster copy of it.
        """
        value = self.get(ns, key, spill=spill)
        if value is not None:
            return value
        cache_key = (ns, key)
        with self._lock:
            gate = self._computing.get(cache_key)
            if gate is None:
                gate = self._computing[cache_key] = _Computation()
            gate.users += 1
        try:
            with gate.lock:
                with self._lock:
                    entry = self._entries.get(cache_key)
                if entry is not None:  # another thread finished it while we waited
                    return entry.value
                value = compute()
                self.put(ns, key, value, nbytes, spill=spill)
                if spill is not None and isinstance(value, np.ndarray):
                    self._spill(_Entry(value, 0, spill))
                return value
        finally:
            with self._lock:
                gate.users -= 1
                # A waiter may still hold this gate even after an exception,
                # eviction or an oversized result. Keep new callers on the
                # same lock until the last registered caller has left.
                if gate.users == 0:
                    self._computing.pop(cache_key, None)


#: The process-wide budget; stores, histories and sessions use it unless given another.
BUDGET = MemoryBudget()


def configure(limit_bytes: int) -> None:
    """Set the budget for the whole process (a setting, WP35)."""
    BUDGET.set_limit(limit_bytes)


# -- the editor's own size ---------------------------------------------------------

#: The editor's resident size above which it logs a warning. Before the fix of
#: 2026-10-20 it reached 3 GB on a 47-minute project (owner's MacBook); after
#: it, the heaviest path measured ~1 GB (docs/MEMORY.md).
RSS_WARN_BYTES = 3 * 1024**3
#: How often the watcher looks, and how much more it must grow before a
#: second warning (so a big project does not log every 30 s).
RSS_WATCH_S = 30.0
RSS_WARN_STEP = 512 * 1024**2


class RssWatch:
    """Logs ``log.memory.high`` when ``read()`` passes ``limit``, and again
    each time it grows by ``step`` more."""

    def __init__(self, read: Callable[[], int | None], limit: int = RSS_WARN_BYTES,
                 step: int = RSS_WARN_STEP, worker_peak: Callable[[], int] = lambda: 0):
        self._read, self.limit, self.step = read, int(limit), int(step)
        self._worker_peak = worker_peak
        self._next = self.limit

    def check(self) -> bool:
        """True when it warned."""
        now = self._read()
        if now is None or now <= self._next:
            return False
        self._next = now + self.step
        log.warning(t("log.memory.high", mb=round(now / 1024**2),
                      limit_mb=round(self.limit / 1024**2),
                      cache_mb=round(BUDGET.used / 1024**2),
                      worker_mb=round(self._worker_peak() / 1024**2)))
        return True


def start_rss_watch() -> None:
    """At the editor's start: a daemon thread that runs ``RssWatch``."""
    from . import offload, priority, rss  # noqa: PLC0415 - they import this module

    watch = RssWatch(rss.current, worker_peak=lambda: offload.WORKER_PEAKS["max"])

    def run() -> None:
        while True:
            watch.check()
            threading.Event().wait(RSS_WATCH_S)

    priority.thread(run, "kuulas-rss-watch").start()
