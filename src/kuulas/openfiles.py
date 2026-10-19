"""Which paths macOS hands the app as documents (WP73).

A double-clicked ``Name.kuulas`` folder, a folder dropped on the Dock icon or
"Open with" arrive as an open-files event, not in ``argv``. The event carries
whatever the user selected, so each path is checked before a window is opened
for it. Pure: no GUI toolkit.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

#: The folder extension of a project package (``Session`` creates ``Name.kuulas``).
EXTENSION = ".kuulas"

#: Files a project folder has once it exists (``Session``): either one is enough
#: for a folder that was renamed and lost its extension.
MARKERS = ("manifest.json", "project.sqlite")


def is_project(path: Path) -> bool:
    if not path.is_dir():
        return False
    return path.suffix.lower() == EXTENSION or any((path / m).exists() for m in MARKERS)


def project_paths(raw: Iterable[str | Path]) -> list[str]:
    """The project folders among ``raw``: resolved, in order, without duplicates.
    Files, missing paths and ordinary folders are dropped."""
    seen: list[str] = []
    for item in raw:
        try:
            path = Path(str(item)).resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if is_project(path) and str(path) not in seen:
            seen.append(str(path))
    return seen
