"""Keep files that must not sync out of Dropbox (docs/FORMAT.md, "Sync services").

SQLite's ``-wal`` and ``-shm`` side files change on every edit and are
meaningless without each other; Dropbox uploads them independently of the
main file, so another machine can see a half-written pair. ``caches/`` is
rebuildable bulk. Dropbox skips a path that carries the extended attribute
``com.dropbox.ignored``. ``locks/`` is deliberately never marked: it has to
sync, that is how one machine sees that another has the project open.

Best-effort: no ``xattr`` tool, a path that vanished or a non-Mac all
silently do nothing. The attribute is lost when SQLite deletes and recreates
a side file, so ``Package`` marks again on every open.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

IGNORE_ATTR = "com.dropbox.ignored"
#: Relative to the package folder.
IGNORED = ("project.sqlite-wal", "project.sqlite-shm", "caches")


def mark_package(folder: Path, *, run: Callable = subprocess.run,
                 platform: str = sys.platform) -> None:
    """Mark the package's side files and caches as ignored by Dropbox."""
    if platform != "darwin":
        return
    for name in IGNORED:
        path = folder / name
        if not path.exists():
            continue
        try:
            run(["xattr", "-w", IGNORE_ATTR, "1", str(path)], check=False,
                capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return  # no xattr here: nothing else will work either
