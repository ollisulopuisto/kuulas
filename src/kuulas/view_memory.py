"""A user's view of each project, remembered outside the project (WP35).

Zoom, scroll, the current track, the play cursor and the like are the user's
habits, not part of the edit: they are kept in one JSON file per user, keyed by
the project's manifest id, and never enter the project or its history (so they
create no undo step and change none of the project's bytes).

The file is ``{"version": 1, "projects": {id: view}}`` with the newest project
last. A view is a plain JSON object the UI owns; keys this code does not know
are kept as they are, so a newer or older UI loses nothing. Writes are atomic
(temporary file, rename). A missing or damaged file means no memory: it is
a convenience and must never stop the editor from opening a project.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from .messages import KuulasError, t

log = logging.getLogger("kuulas.view_memory")

#: How many projects are remembered; the least recently written are dropped.
MAX_PROJECTS = 100
#: A view is a dozen numbers; this stops a runaway client from filling the disk.
MAX_VIEW_BYTES = 16_384
MAX_ID_LENGTH = 128

_LOCK = threading.RLock()


class ViewMemoryError(KuulasError, ValueError):
    """A view that cannot be remembered (a message key, so the API can translate)."""


def default_path() -> Path:
    """``$KUULAS_VIEW_MEMORY_FILE`` (tests, portable setups) or
    ``view-memory.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_VIEW_MEMORY_FILE")
    if override:
        return Path(override)
    # Late: desktop imports cli, which imports the session.
    from .desktop import config_dir  # noqa: PLC0415

    return config_dir() / "view-memory.json"


def _check(project_id: object, view: object) -> None:
    ok = isinstance(project_id, str) and 0 < len(project_id) <= MAX_ID_LENGTH
    if not ok:
        raise ViewMemoryError("error.view_memory.bad_id")
    if not isinstance(view, dict):
        raise ViewMemoryError("error.view_memory.not_object")
    try:
        size = len(json.dumps(view, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as e:
        raise ViewMemoryError("error.view_memory.not_json", detail=str(e)) from None
    if size > MAX_VIEW_BYTES:
        raise ViewMemoryError("error.view_memory.too_large", limit=MAX_VIEW_BYTES)


class ViewMemory:
    """The memory file at ``path`` (``default_path()`` when not given)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_path()

    def _load(self) -> dict:
        """The whole file as a dict with a valid ``projects`` map; empty when
        the file is missing or damaged."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"version": 1, "projects": {}}
        except (OSError, UnicodeDecodeError) as e:
            log.warning(t("log.view_memory.unreadable", path=str(self.path),
                          error=str(e)))
            return {"version": 1, "projects": {}}
        if not text.strip():
            return {"version": 1, "projects": {}}
        try:
            data = json.loads(text)
            projects = data["projects"]
            sound = isinstance(projects, dict) and all(
                isinstance(v, dict) for v in projects.values())
            error = "" if sound else "projects must map ids to objects"
        except (ValueError, TypeError, KeyError) as e:
            error = str(e) or "unreadable"
        if error:
            log.warning(t("log.view_memory.damaged", path=str(self.path), error=error))
            return {"version": 1, "projects": {}}
        return data

    def get(self, project_id: str) -> dict | None:
        """The remembered view of this project, or None."""
        with _LOCK:
            return self._load()["projects"].get(project_id)

    def put(self, project_id: str, view: dict) -> None:
        """Remember ``view`` (replacing the old one) and make the project the
        newest. Raises ``ViewMemoryError`` (a ``ValueError``) for junk, ``OSError``
        when the file cannot
        be written (the old file is then untouched)."""
        _check(project_id, view)
        with _LOCK:
            data = self._load()
            projects = data["projects"]
            projects.pop(project_id, None)
            projects[project_id] = view
            while len(projects) > MAX_PROJECTS:
                del projects[next(iter(projects))]
            self._write(json.dumps(data, ensure_ascii=False))

    def _write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + ".",
                                    suffix=".partial")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(text)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(name)
            raise
