"""The clipboard history on disk (WP46 wiring): one JSON file per user.

Every kuulas process of this user reads and writes the same file, which is
what lets an entry copied in one project be pasted in another. The file holds
references only (``clipboard``), so it stays small. Writes are atomic (a
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

#: How many entries the history keeps; pinned ones are never dropped.
MAX_ENTRIES = 50

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


def entry_dict(entry: Entry) -> dict:
    """An entry as plain JSON data for the API."""
    return json.loads(clipboard.to_json(entry))


class ClipboardStore:
    """The history file at ``path`` (``default_path()`` when not given)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_path()

    def load(self) -> ClipboardHistory:
        """The history in the file; empty when it is missing or damaged."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ClipboardHistory(MAX_ENTRIES)
        except (OSError, UnicodeDecodeError) as e:
            log.warning(t("log.clipboard.unreadable", path=str(self.path), error=str(e)))
            return ClipboardHistory(MAX_ENTRIES)
        if not text.strip():
            return ClipboardHistory(MAX_ENTRIES)
        try:
            history = ClipboardHistory.from_json(text)
            # Parsing is lazy about shapes (a string where a list belongs); a
            # round trip proves every entry is usable.
            history.to_json()
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as e:
            log.warning(t("log.clipboard.damaged", path=str(self.path), error=str(e)))
            return ClipboardHistory(MAX_ENTRIES)
        # The limit is ours, not the file's: a hand-edited or newer file
        # cannot make the history grow without bound.
        history.max_entries = MAX_ENTRIES
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

    def update(self, change: Callable[[ClipboardHistory], _T]) -> _T:
        """Load, apply ``change`` to the history, write it back; return what
        ``change`` returned. Raises ``OSError`` when the file cannot be written
        (the old file is then untouched)."""
        with _LOCK:
            history = self.load()
            result = change(history)
            history.max_entries = MAX_ENTRIES
            self._write(history.to_json())
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
