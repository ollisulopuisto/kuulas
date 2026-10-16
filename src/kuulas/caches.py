"""``caches/``: things kuulas can always compute again (docs/FORMAT.md).

A cache file is named by what it was computed from, never by a media name
or path: ``caches/<kind>/<key>.<ext>``, where ``key`` is the SHA-256 of
``{inputs, params, algorithm}``. Bump an algorithm's ``@version`` whenever
its code changes what it computes, and every old entry stops matching.

The folder may be deleted at any time; it is left out of backups and
archives. A cache whose key cannot be computed is not used (fail closed),
and every recompute is logged.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .messages import KuulasError

KINDS = ("peaks", "onsets", "analysis", "render")


class CacheKeyError(KuulasError, ValueError):
    """A cache key could not be computed; the caller recomputes without the cache."""


def key(inputs: list[str], params: dict[str, Any], algorithm: str) -> str:
    """``inputs``: media SHA-256s or blob hashes. ``algorithm``: ``name@version``.

    Fails closed (``CacheKeyError``): an input that is not a non-empty string
    (a media row without its hash), params JSON cannot hold, or an algorithm
    without a version would give a key that proves nothing.
    """
    if not isinstance(algorithm, str) or "@" not in algorithm.strip("@"):
        raise CacheKeyError("error.cache.no_key", algorithm=str(algorithm))
    if any(not isinstance(i, str) or not i for i in inputs):
        raise CacheKeyError("error.cache.no_key", algorithm=algorithm)
    try:
        raw = json.dumps({"inputs": list(inputs), "params": params,
                          "algorithm": algorithm},
                         sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise CacheKeyError("error.cache.no_key", algorithm=algorithm) from None
    return hashlib.sha256(raw.encode()).hexdigest()


def path(root: str | Path, kind: str, cache_key: str, ext: str) -> Path:
    return Path(root) / kind / f"{cache_key}.{ext}"


def write_atomic(target: Path, write) -> None:
    """``write(file)`` into a temp file beside ``target``, then rename: a
    crash leaves either the old entry or none, never half of one."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.partial")
    with tmp.open("wb") as f:
        write(f)
    tmp.replace(target)
