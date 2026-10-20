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


def _sizeof(value: Any) -> int:
    """Bytes of an array, or of a dict of arrays; anything else needs ``nbytes``."""
    if isinstance(value, dict):
        return sum(_sizeof(v) for v in value.values())
    return int(value.nbytes)


class _Entry:
    __slots__ = ("nbytes", "spill", "value")

    def __init__(self, value: Any, nbytes: int, spill: Path | None):
        self.value, self.nbytes, self.spill = value, nbytes, spill


class MemoryBudget:
    def __init__(self, limit_bytes: int = DEFAULT_LIMIT):
        self.limit = int(limit_bytes)
        self.used = 0
        self._entries: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self._lock = threading.RLock()
        #: One lock per key being computed, so two threads wanting the same
        #: envelope compute it once (a speech lane per core asks together).
        self._computing: dict[tuple[str, str], threading.Lock] = {}
        self._counts: dict[str, dict[str, int]] = {}
        self._lookups = 0

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
                self.used -= old.nbytes
            if size > self.limit:
                self._spill(_Entry(value, size, spill))
                return
            self._entries[ns, key] = _Entry(value, size, spill)
            self.used += size
            self._evict()

    def discard(self, ns: str, key: str) -> None:
        with self._lock:
            entry = self._entries.pop((ns, key), None)
            if entry is not None:
                self.used -= entry.nbytes

    def discard_prefix(self, ns: str, prefix: str) -> None:
        """Discard all entries in ``ns`` whose key starts with ``prefix``."""
        with self._lock:
            to_remove = [k for k in self._entries
                         if k[0] == ns and k[1].startswith(prefix)]
            for k in to_remove:
                entry = self._entries.pop(k, None)
                if entry is not None:
                    self.used -= entry.nbytes

    def set_limit(self, limit_bytes: int) -> None:
        with self._lock:
            self.limit = int(limit_bytes)
            self._evict()

    def _evict(self) -> None:
        while self.used > self.limit and self._entries:
            _, entry = self._entries.popitem(last=False)
            self.used -= entry.nbytes
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
        with self._lock:
            gate = self._computing.setdefault((ns, key), threading.Lock())
        with gate:
            with self._lock:
                entry = self._entries.get((ns, key))
            if entry is not None:  # another thread finished it while we waited
                return entry.value
            value = compute()
            self.put(ns, key, value, nbytes, spill=spill)
            if spill is not None and isinstance(value, np.ndarray):
                self._spill(_Entry(value, 0, spill))
        with self._lock:
            self._computing.pop((ns, key), None)
        return value


#: The process-wide budget; stores, histories and sessions use it unless given another.
BUDGET = MemoryBudget()


def configure(limit_bytes: int) -> None:
    """Set the budget for the whole process (a setting, WP35)."""
    BUDGET.set_limit(limit_bytes)
