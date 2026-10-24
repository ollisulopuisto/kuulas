"""How far an analysis task is (owner, 2026-10-24: a progress bar on Level blocks, like
the structured progress of the podcast tools).

A task calls ``report(fraction, stage, **detail)``: ``fraction`` 0..1, ``stage`` a short
word the editor turns into text (``tracks``, ``blocks``), ``detail`` plain numbers for
that text (``done``, ``total``). In the analysis worker (a process of its own) the report
is written to the file the editor named in ``KUULAS_PROGRESS_FILE``, atomically; the
editor reads it while it waits (``read``). Inline (tests, a worker that could not start)
it goes straight to the callback ``offload.call(..., on_progress=...)`` set. Without
either it does nothing, so a task may report always. Stdlib only: the worker imports this
before anything heavy.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path

PROGRESS_ENV = "KUULAS_PROGRESS_FILE"

#: The inline callback of the one analysis running here now (a plain global: the
#: task's own pool threads report too). Set and cleared by ``offload.call``.
_CALLBACK: Callable[[float, str, dict], None] | None = None
_LOCK = threading.Lock()


def set_callback(callback: Callable[[float, str, dict], None] | None) -> None:
    global _CALLBACK  # noqa: PLW0603 - one analysis at a time runs inline
    _CALLBACK = callback


def report(fraction: float, stage: str = "", **detail: float) -> None:
    """Say how far the task is. Never raises: progress is only for show."""
    fraction = min(1.0, max(0.0, float(fraction)))
    callback = _CALLBACK
    if callback is not None:
        try:
            callback(fraction, stage, dict(detail))
        except Exception:  # noqa: BLE001 - a broken listener must not stop the analysis
            return
        return
    target = os.environ.get(PROGRESS_ENV)
    if not target:
        return
    path = Path(target)
    try:
        with _LOCK:
            temp = path.with_suffix(".part")
            temp.write_text(json.dumps({"fraction": fraction, "stage": stage,
                                        "detail": detail}), encoding="utf-8")
            temp.replace(path)
    except OSError:
        return


def read(path: Path) -> tuple[float, str, dict] | None:
    """What the file says: ``(fraction, stage, detail)``, or None when there is nothing
    (yet), or it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (float(data["fraction"]), str(data.get("stage", "")),
                dict(data.get("detail", {})))
    except (OSError, ValueError, KeyError, TypeError):
        return None
