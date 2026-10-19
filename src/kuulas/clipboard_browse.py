"""Looking into other projects' clipboards (WP65 step 5, "spelunking").

The Clipboard tab can list the entries of any other project and adopt one into
the open project. This module is the *read-only* side: it reads another
project's ``clipboard.json`` straight from its folder. It never takes the
project's lock, never opens its database, never writes a byte there, so a
project that is open in another window (or on another Mac, through Dropbox) is
unaffected, and a hostile or half-synced folder can at worst give an empty list.

**The path rule** (``project_folder``), because the path comes from the page:

1. it is text, non-empty, at most 4096 characters, with no NUL;
2. it is absolute (no ``~``, no relative path);
3. it has no ``..`` component, even one that would land on a project;
4. after resolving links it is an existing directory named ``*.kuulas`` that
   holds a regular ``manifest.json``, i.e. it is a kuulas project;
5. only ``<folder>/clipboard.json`` is ever read: exactly that name (a
   "conflicted copy" is another file), a regular file (not a link), under
   ``MAX_BYTES``.

Anything else is ``error.clipboard.bad_project`` (HTTP 400). A missing,
unreadable or damaged ``clipboard.json`` is not an error: it is an empty list.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from . import clipboard_link
from .clipboard import Entry
from .clipboard_store import PROJECT_FILE, ClipboardStore
from .ops import EditError
from .resume import read_resume

log = logging.getLogger("kuulas.clipboard")

#: A clipboard bigger than this is not read (it is a convenience file; the
#: biggest real ones, with transcript text, are a few megabytes).
MAX_BYTES = 64 * 1024 * 1024
MAX_PATH = 4096
PROJECT_SUFFIX = ".kuulas"


def _bad(path: object) -> EditError:
    return EditError("error.clipboard.bad_project", path=str(path)[:200])


def project_folder(path: object) -> Path:
    """The resolved folder of the kuulas project at ``path``, or ``EditError``
    (``error.clipboard.bad_project``). See the module docstring for the rule."""
    if not isinstance(path, str) or not path.strip() or "\0" in path:
        raise _bad(path)
    if len(path) > MAX_PATH:
        raise _bad(path)
    raw = Path(path)
    if not raw.is_absolute() or ".." in raw.parts:
        raise _bad(path)
    try:
        folder = raw.resolve(strict=True)
        isproject = (folder.is_dir() and folder.name.endswith(PROJECT_SUFFIX)
                     and (folder / "manifest.json").is_file())
    except (OSError, RuntimeError):
        raise _bad(path) from None
    if not isproject:
        raise _bad(path)
    return folder


def clipboard_file(folder: Path) -> Path | None:
    """The folder's ``clipboard.json`` when it is a plain readable file, else None."""
    file = folder / PROJECT_FILE
    try:
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_BYTES:
            return None
    except OSError:
        return None
    return file


def read_entries(folder: Path) -> list[Entry]:
    """The entries of the project at ``folder`` (already validated), newest
    first; empty when the file is missing, damaged, a link or too big. Reads one
    file and nothing else."""
    file = clipboard_file(folder)
    if file is None:
        return []
    return list(ClipboardStore(file, writable=False).load().entries())


def last_opened(folder: Path) -> str:
    """When the project was last worked in, UTC ISO: the time its
    ``resume.json`` says, else the database's modification time, else ""."""
    resume = read_resume(folder)
    if resume and isinstance(resume.get("saved_at"), str):
        return resume["saved_at"]
    try:
        stamp = (folder / "project.sqlite").stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(stamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def recent_projects(recents: list[str], current: str | Path) -> list[dict]:
    """The recent projects other than ``current``, in the given (most recent
    first) order, each ``{name, path, last_opened, entries}``. The entry count is
    read now, from the file, so it is never stale; a project that cannot be read
    still lists, with 0."""
    out = []
    for path in recents:
        if clipboard_link.same_folder(path, current):
            continue
        try:
            folder = project_folder(path)
        except EditError:
            continue  # moved or deleted since it was remembered
        out.append({"name": folder.stem, "path": path, "last_opened": last_opened(folder),
                    "entries": len(read_entries(folder))})
    return out
