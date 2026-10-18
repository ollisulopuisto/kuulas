"""``resume.json``: where the user left off, kept in the project folder (docs/FORMAT.md).

The per-user view memory lives outside the project, so it does not follow a
project that two Macs share through Dropbox. This small file does: playhead,
in/out marks, focus track, zoom and scroll, with the time, host and user that
wrote it. It is **not project state**: never in the history or the database, no
undo step, no change to ``project.sqlite``. The lock guarantees one writer at a
time, so the file is a plain atomic rewrite; if a sync service still makes a
"conflicted copy", that copy is never read.

Writing is a convenience and never raises: a failure is logged as a warning.
"""

from __future__ import annotations

import getpass
import json
import logging
import math
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .messages import t
from .package import write_json_atomic

log = logging.getLogger("kuulas.resume")

RESUME_NAME = "resume.json"
#: At most one write this often while the user works (a Dropbox upload per
#: cursor move would be wasteful); close and an explicit flush write at once.
WRITE_INTERVAL_S = 5.0

#: resume.json key <- view-memory key.
_FIELDS = {"playhead": "playhead", "in": "inPoint", "out": "outPoint",
           "focus_track": "focusTrack", "zoom": "zoom", "scroll": "scroll"}


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(key: str, value: object) -> bool:
    if key == "focus_track":
        return isinstance(value, str)
    return (isinstance(value, int | float) and not isinstance(value, bool)
            and math.isfinite(value))


def record_of(view: dict, *, host: str, user: str, saved_at: str) -> dict:
    """The resume record for a UI view; values of the wrong type are left out."""
    out: dict = {"version": 1, "saved_at": saved_at, "host": host, "user": user}
    for key, source in _FIELDS.items():
        value = view.get(source)
        if _clean(key, value):
            out[key] = value
    return out


def read_resume(folder: str | Path) -> dict | None:
    """The folder's resume record, or None when missing, damaged, or without a
    ``saved_at`` (it could not be compared with anything). Only the exact name
    ``resume.json`` is read: a "conflicted copy" is another file."""
    try:
        data = json.loads((Path(folder) / RESUME_NAME).read_text(encoding="utf-8"))
        datetime.strptime(data["saved_at"], "%Y-%m-%dT%H:%M:%SZ")  # noqa: DTZ007
    except (OSError, ValueError, TypeError, KeyError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


class ResumeWriter:
    """Writes ``resume.json`` for one open project, throttled."""

    def __init__(self, folder: str | Path, *, enabled: bool = True,
                 interval: float = WRITE_INTERVAL_S) -> None:
        self.folder = Path(folder)
        self.enabled = enabled
        self.interval = interval
        self._lock = threading.RLock()
        self._view: dict | None = None
        self._dirty = False
        self._last_write = -math.inf
        self._timer: threading.Timer | None = None
        try:
            self._user = getpass.getuser()
        except (OSError, KeyError):
            self._user = ""
        self._host = socket.gethostname()

    @property
    def view(self) -> dict | None:
        """The last view handed to ``remember`` (a copy)."""
        with self._lock:
            return dict(self._view) if self._view is not None else None

    def remember(self, view: dict, *, now: bool = False) -> None:
        """Note the latest view; write it now if the last write is old enough or
        ``now``, otherwise a timer writes it when the interval has passed."""
        if not self.enabled:
            return
        with self._lock:
            self._view = dict(view)
            self._dirty = True
            wait = self._last_write + self.interval - time.monotonic()
            if now or wait <= 0:
                self._write()
            elif self._timer is None:
                self._timer = threading.Timer(wait, self._on_timer)
                self._timer.daemon = True
                self._timer.start()

    def _on_timer(self) -> None:
        with self._lock:
            self._timer = None
            self._write()

    def _write(self) -> None:
        if not self._dirty or self._view is None:
            return
        self._dirty = False
        self._last_write = time.monotonic()
        record = record_of(self._view, host=self._host, user=self._user,
                           saved_at=now_iso())
        try:
            write_json_atomic(self.folder / RESUME_NAME, record)
        except OSError as e:
            log.warning(t("log.resume.write_failed", path=str(self.folder), error=str(e)))

    def close(self, playhead: int | None = None) -> None:
        """Write the last view at once, with ``playhead`` in place of the
        remembered one (the engine's, when the window closed while playing).
        Nothing remembered this session means nothing is written: a project
        that was only opened keeps the position it had."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self.enabled or self._view is None:
                return
            if playhead is not None and _clean("playhead", playhead):
                self._view["playhead"] = int(playhead)
                self._dirty = True
            self._write()
