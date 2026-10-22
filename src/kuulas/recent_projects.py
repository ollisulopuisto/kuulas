"""The recent projects list (WP65), logic only.

The projects the user opened lately, as pure functions over lists of path
strings, most recent first: opening a project moves it to the front and the
oldest overflow falls off, the paths that no longer exist are filtered out
by a caller-supplied ``exists`` (the list functions do no I/O of their own), and
the display names the "Other projects" list shows drop the parent folder
and the ``.kuulas`` suffix, sortable by name.

``os.path.normpath`` decides which spellings are the same project, the way
a folder can be written with a trailing slash or a ``./`` inside and still
be that folder. No kuulas imports, no I/O, no user-facing strings: a bad
limit is a plain ``ValueError``. No function touches its input.

The records part keeps what is remembered beside each path (opened time, track
count, length, size); its only I/O is ``folder_size``, which reads and is capped.
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


# -- records: what is remembered beside each path ----------------------------------

#: The facts kept per project, beside ``path`` and ``opened_utc``. All optional.
META_FIELDS = ("tracks", "duration_s", "size_bytes")

#: How many directory entries ``folder_size`` looks at before giving up.
SIZE_MAX_ENTRIES = 20_000


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_amount(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def normalize_record(item: object) -> dict | None:
    """A clean record from what the recents file holds, or None.

    A bare string is the old format: just the path. A dict keeps ``path``,
    ``opened_utc`` and the valid ``META_FIELDS``; unknown or invalid keys are
    dropped, so a damaged value never reaches the start page.
    """
    if isinstance(item, str):
        return {"path": item} if item else None
    if not isinstance(item, dict):
        return None
    path = item.get("path")
    if not isinstance(path, str) or not path:
        return None
    record: dict = {"path": path}
    if isinstance(item.get("opened_utc"), str):
        record["opened_utc"] = item["opened_utc"]
    if _is_count(item.get("tracks")):
        record["tracks"] = item["tracks"]
    for key in ("duration_s", "size_bytes"):
        if _is_amount(item.get(key)):
            record[key] = item[key]
    return record


def make_record(path: str, opened_utc: str | None = None, **meta: float | None) -> dict:
    """A record for ``path``; ``None`` facts are left out."""
    record: dict = {"path": path}
    if opened_utc is not None:
        record["opened_utc"] = opened_utc
    for key in META_FIELDS:
        if meta.get(key) is not None:
            record[key] = meta[key]
    return normalize_record(record) or {"path": path}


def merge_record(existing: list[dict], new: dict, limit: int = 20) -> list[dict]:
    """``merge_recent`` for records: ``new`` goes first, and the facts an earlier
    copy of the same project had that ``new`` does not carry are kept.
    ``existing`` is left alone."""
    if limit < 1:
        msg = f"recent projects limit must be at least 1, not {limit}"
        raise ValueError(msg)
    norm = os.path.normpath(new["path"])
    merged = dict(new)
    for old in existing:
        if os.path.normpath(old["path"]) == norm:
            for key in ("opened_utc", *META_FIELDS):
                if key in old and key not in merged:
                    merged[key] = old[key]
    rest = [dict(r) for r in existing if os.path.normpath(r["path"]) != norm]
    return [merged, *rest][:limit]


def update_record(existing: list[dict], path: str, **meta: float | None) -> list[dict]:
    """A new list with the facts of ``path`` replaced, order and ``opened_utc``
    untouched. A ``None`` fact is left as it was; a path not in the list changes
    nothing."""
    norm = os.path.normpath(path)
    result = []
    for old in existing:
        record = dict(old)
        if os.path.normpath(record["path"]) == norm:
            for key in META_FIELDS:
                if meta.get(key) is not None:
                    record[key] = meta[key]
            record = normalize_record(record) or record
        result.append(record)
    return result


def remove_record(existing: list[dict], path: str) -> list[dict]:
    """A new list without the project at ``path`` (any spelling of it). Only the
    list changes; a path that is not in it changes nothing."""
    norm = os.path.normpath(path)
    return [dict(r) for r in existing if os.path.normpath(r["path"]) != norm]


def drop_missing(existing: list[dict], exists: Callable[[str], bool]) -> list[dict]:
    """A new list of the records whose folder ``exists`` accepts."""
    return [dict(r) for r in existing if exists(r["path"])]


def insert_record(existing: list[dict], record: dict, index: int,
                  limit: int = 20) -> list[dict]:
    """A new list with ``record`` at ``index`` (clamped to the list), any earlier
    copy of the project removed first. Undo of a removal."""
    rest = remove_record(existing, record["path"])
    at = max(0, min(index, len(rest)))
    return [*rest[:at], dict(record), *rest[at:]][:limit]


def replace_path(existing: list[dict], old: str, new: str) -> list[dict]:
    """A new list where the project at ``old`` is at ``new`` instead: same place,
    same remembered facts (the project was moved, not changed). If ``new`` is
    already listed, that copy goes and this one stays in place."""
    norm = os.path.normpath(old)
    if not any(os.path.normpath(r["path"]) == norm for r in existing):
        return [dict(r) for r in existing]
    target = os.path.normpath(new)
    result = []
    for record in existing:
        copy = dict(record)
        if os.path.normpath(copy["path"]) == norm:
            copy["path"] = new
        elif os.path.normpath(copy["path"]) == target:
            continue
        result.append(copy)
    return result


def folder_size(path: str | os.PathLike[str],
                max_entries: int = SIZE_MAX_ENTRIES) -> int | None:
    """The bytes of the files under ``path``, symbolic links not followed (a
    linked medium is not part of the project). None when the folder cannot be
    read or has more than ``max_entries`` entries: a huge tree is not walked to
    the end for a number on a start page. Reads only."""
    total = 0
    seen = 0
    stack = [os.fspath(path)]
    try:
        while stack:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    seen += 1
                    if seen > max_entries:
                        return None
                    if entry.is_symlink():
                        continue
                    if entry.is_dir():
                        stack.append(entry.path)
                    elif entry.is_file():
                        total += entry.stat().st_size
    except OSError:
        return None
    return total
