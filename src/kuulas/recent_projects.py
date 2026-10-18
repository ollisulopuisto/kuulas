"""The recent projects list (WP65), logic only.

The projects the user opened lately, as pure functions over lists of path
strings, most recent first: opening a project moves it to the front and the
oldest overflow falls off, the paths that no longer exist are filtered out
by a caller-supplied ``exists`` (this module does no I/O of its own), and
the display names the "Other projects" list shows drop the parent folder
and the ``.kuulas`` suffix, sortable by name.

``os.path.normpath`` decides which spellings are the same project, the way
a folder can be written with a trailing slash or a ``./`` inside and still
be that folder. No kuulas imports, no I/O, no user-facing strings: a bad
limit is a plain ``ValueError``. No function touches its input.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import PurePath


def merge_recent(existing: list[str], new_path: str,
                 limit: int = 20) -> list[str]:
    """A new most-recent-first list with ``new_path`` moved to the front.

    Every earlier copy of the project — the same ``os.path.normpath`` —
    is removed whatever its spelling; the new spelling is the one kept.
    The list is then cut to ``limit``, the new path included in the cut;
    ``limit`` below one raises ``ValueError``. ``existing`` is left alone.
    """
    if limit < 1:
        msg = f"recent projects limit must be at least 1, not {limit}"
        raise ValueError(msg)
    norm = os.path.normpath(new_path)
    return [new_path, *(p for p in existing if os.path.normpath(p) != norm)][:limit]


def live_recent(paths: list[str], exists: Callable[[str], bool]) -> list[str]:
    """The paths ``exists`` accepts, in their order, one per project.

    A normalised path is seen once — the first spelling wins — and is kept
    when ``exists`` accepts that spelling, so every returned path is one
    ``exists`` was called with and said true about.
    """
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        norm = os.path.normpath(path)
        if norm in seen:
            continue
        seen.add(norm)
        if exists(path):
            result.append(path)
    return result


def display_name(path: str) -> str:
    """The folder name alone: no parent, no trailing ``.kuulas``.

    ``/a/b/Vikasietotila s13e04.kuulas/`` is ``Vikasietotila s13e04``. An
    empty path is an empty name.
    """
    if not path:
        return ""
    name = PurePath(path).name
    return name[: -len(".kuulas")] if name.endswith(".kuulas") else name


def sort_by_name(paths: list[str]) -> list[str]:
    """A new list sorted case-insensitively by display name, ties by path.

    ``casefold`` rather than ``lower`` folds the Finnish letters properly;
    the full path string breaks the ties, so the order is total.
    """
    return sorted(paths, key=lambda p: (display_name(p).casefold(), p))
