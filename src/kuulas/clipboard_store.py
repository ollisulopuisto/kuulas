"""The clipboard on disk (WP46 wiring, WP65): one JSON file per project, and one per user.

Since WP65 each project keeps its own clipboard in ``<project>.kuulas/clipboard.json``
(``project_path``), written only by the instance that holds the project's lock.
The per-user file (``default_path``) is the *shared* store: the entries the user
marked as worth sharing, and the old history that has not yet moved to the
project it came from. The files hold references only, so they stay small.
Writes are atomic (a
temporary file renamed over the old one), so a crash leaves the old history.
A missing or damaged file is an empty history: the clipboard is a convenience
and must never stop an edit or the editor from starting.

Each change reads the file again first, so a second window's entries are not
overwritten by a stale copy in memory.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from . import clipboard
from .clipboard import ClipboardHistory, Entry
from .messages import t

log = logging.getLogger("kuulas.clipboard")

#: A project's clipboard file inside the ``.kuulas`` folder. Not project state
#: (docs/FORMAT.md): it must sync with Dropbox, so syncmark never marks it.
PROJECT_FILE = "clipboard.json"

_T = TypeVar("_T")
#: One writer at a time inside this process (other processes: last write wins
#: on a whole-file basis, which for a user's own clipboard is acceptable).
_LOCK = threading.RLock()


def default_path() -> Path:
    """The user's clipboard file: ``$KUULAS_CLIPBOARD_FILE`` (tests, portable
    setups) or ``clipboard.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_CLIPBOARD_FILE")
    if override:
        return Path(override)
    # Late: desktop imports cli, which imports the session, which imports this.
    from .desktop import config_dir  # noqa: PLC0415

    return config_dir() / "clipboard.json"


def project_path(folder: str | Path) -> Path:
    """The clipboard file of the project at ``folder``. Only this exact name is
    ever read: a "conflicted copy" is another file."""
    return Path(folder) / PROJECT_FILE


def entry_dict(entry: Entry) -> dict:
    """An entry as plain JSON data for the API."""
    return json.loads(clipboard.to_json(entry))


class ClipboardStore:
    """The clipboard file at ``path`` (``default_path()`` when not given).

    ``writable=False`` (a read-only project) never touches the disk: the
    entries live in memory for this window, so copy and paste still work.
    ``soft=True`` (a project's own file) turns a failed write into a logged
    warning and ``write_error`` instead of an exception: the clipboard is a
    convenience and must not stop an edit.
    """

    def __init__(self, path: str | Path | None = None, *, writable: bool = True,
                 soft: bool = False) -> None:
        self.path = Path(path) if path is not None else default_path()
        self.writable = writable
        self.soft = soft
        #: The last failed write's message, None after a good one (soft stores).
        self.write_error: str | None = None
        self._memory: ClipboardHistory | None = None

    def load(self) -> ClipboardHistory:
        """The history in the file; empty when it is missing or damaged."""
        if self._memory is not None:
            return ClipboardHistory.from_json(self._memory.to_json())
        return self._read()

    def _read(self) -> ClipboardHistory:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ClipboardHistory()
        except (OSError, UnicodeDecodeError) as e:
            log.warning(t("log.clipboard.unreadable", path=str(self.path), error=str(e)))
            return ClipboardHistory()
        if not text.strip():
            return ClipboardHistory()
        try:
            history = ClipboardHistory.from_json(text)
            # Parsing is lazy about shapes (a string where a list belongs); a
            # round trip proves every entry is usable.
            history.to_json()
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
            log.warning(t("log.clipboard.damaged", path=str(self.path), error=str(e)))
            return ClipboardHistory()
        # No limit is ours to impose and none is the file's: nothing is
        # dropped unless the user clears old entries.
        history.max_entries = None
        return history

    def stamp(self) -> tuple[int, int] | None:
        """``(mtime_ns, size)`` of the file, None when there is none. A write
        is an atomic rename, so any change by another window (another process
        on the same user file) changes this; the live channel compares it to
        tell the UI to read the history again."""
        try:
            info = self.path.stat()
        except OSError:
            return None
        return info.st_mtime_ns, info.st_size

    def update(self, change: Callable[[ClipboardHistory], _T]) -> _T | None:
        """Load, apply ``change`` to the history, write it back; return what
        ``change`` returned. A hard store raises ``OSError`` when the file cannot
        be written (the old file is then untouched); a soft one logs it, sets
        ``write_error`` and returns None. A store that may not write keeps the
        change in memory only."""
        with _LOCK:
            history = self._memory if self._memory is not None else self._read()
            result = change(history)
            history.max_entries = None
            if not self.writable:
                self._memory = history
                return result
            try:
                self._write(history.to_json())
            except OSError as e:
                if not self.soft:
                    raise
                self.write_error = str(e)
                # Keep it for this window rather than lose the copy.
                self._memory = history
                log.warning(t("log.clipboard.write_failed", path=str(self.path),
                              error=str(e)))
                return None
            self.write_error = None
            self._memory = None
            return result

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
