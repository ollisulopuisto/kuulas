"""Series storage: people and interviews as one small JSON file each (WP41).

A series folder (WP38) holds ``people/`` and ``interviews/``, one file per
item named ``<id>.json`` (docs/FORMAT.md, "People, interviews and bits").
Sync tools (Dropbox, Syncthing, iCloud, OneDrive) work file by file, so two
machines editing different items never meet, and a real conflict touches
exactly one item. The tool then leaves a *conflicted copy* beside it under
another name; those are never read as items, and ``conflicts`` reports them
so the owner can decide. Nothing here deletes a conflicted copy.

Only the storage lives here: the series folder itself and its UI are WP38.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from .history import History
from .messages import KuulasError, t
from .package import write_json_atomic
from .people import Passage

log = logging.getLogger("kuulas.series")

#: What a series folder holds. ``bits`` joins them in WP42.
KINDS = ("people", "interviews")

#: Item ids are UUIDv7s (``db.uuid7``). Anything else is refused on write, so an
#: id can never climb out of its folder or collide with a sync tool's suffix.
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
#: A file that starts with an id and carries anything more before ``.json``:
#: "<id> (Olli's conflicted copy …)", "<id>.sync-conflict-…", "<id> 2", "<id>-HOST".
_COPY = re.compile(r"^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
                   r"(.+)\.json$")


class SeriesError(KuulasError, ValueError):
    """The request names a kind or an id a series folder cannot hold."""


@dataclass(frozen=True)
class Conflict:
    """A file in a series folder that is not a clean item.

    ``reason``: ``conflict`` (a sync tool's copy of an item), ``unreadable``
    (not valid JSON, or not an object) or ``mismatched`` (the item inside
    names another id than its file).
    """

    kind: str
    item_id: str
    path: Path
    reason: str
    original_exists: bool
    identical: bool  # same content as the item itself: safe to delete

    def __str__(self) -> str:
        key = {"conflict": "series.conflict", "unreadable": "series.unreadable",
               "mismatched": "series.mismatched"}[self.reason]
        return t(key, kind=self.kind, item_id=self.item_id, name=self.path.name)


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class SeriesStore:
    """The people and interviews of one series folder."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)

    def _dir(self, kind: str) -> Path:
        if kind not in KINDS:
            raise SeriesError("error.series.bad_kind", kind=kind)
        return self.folder / kind

    def _file(self, kind: str, item_id: str) -> Path:
        if not _ID.match(str(item_id)):
            raise SeriesError("error.series.bad_id", item_id=item_id)
        return self._dir(kind) / f"{item_id}.json"

    def put(self, kind: str, item: dict) -> None:
        """Write one item atomically: the old file or the new one, never half."""
        path = self._file(kind, item.get("id", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, item)

    def get(self, kind: str, item_id: str) -> dict | None:
        path = self._file(kind, item_id)
        item = _read(path)
        return item if item is not None and item.get("id") == item_id else None

    def delete(self, kind: str, item_id: str) -> None:
        self._file(kind, item_id).unlink(missing_ok=True)

    def items(self, kind: str) -> list[dict]:
        """Every clean item of ``kind``, by id. Conflicted copies and files that
        cannot be read are left out; ``conflicts`` lists them."""
        folder = self._dir(kind)
        if not folder.is_dir():
            return []
        out = []
        for path in sorted(folder.glob("*.json")):
            if not _ID.match(path.stem):
                continue
            item = _read(path)
            if item is not None and item.get("id") == path.stem:
                out.append(item)
        return out

    def conflicts(self) -> list[Conflict]:
        """Everything in the series folder that needs a look, for the UI to show."""
        found = []
        for kind in KINDS:
            folder = self._dir(kind)
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.json")):
                found.extend(self._inspect(kind, path))
        return found

    def _inspect(self, kind: str, path: Path) -> list[Conflict]:
        copy = _COPY.match(path.name)
        if copy:
            item_id = copy.group(1)
            original = _read(path.with_name(f"{item_id}.json"))
            mine = _read(path)
            return [Conflict(kind, item_id, path, "conflict",
                             path.with_name(f"{item_id}.json").exists(),
                             original is not None and original == mine)]
        if not _ID.match(path.stem):
            return []  # not ours: a sync tool's own file, a note
        item = _read(path)
        if item is None:
            return [Conflict(kind, path.stem, path, "unreadable", True, False)]
        if item.get("id") != path.stem:
            return [Conflict(kind, path.stem, path, "mismatched", True, False)]
        return []


def passages_in_projects(projects: list[str | Path], person: str) -> list[Passage]:
    """What ``person`` said in each of a series' projects, in the order given.

    Each project is read through its own read-only connection: no lock is
    taken and nothing is migrated, so it works while a project is open on
    another machine. A project that cannot be read costs that project, not
    the answer (it is logged).

    TODO(WP37/WP38): the usage marks ("used in Ep 3, published v2") come from
    each project's usage file; neither exists yet, so passages carry only
    their recording ranges.
    """
    out = []
    for project in map(Path, projects):
        try:
            history = History(project / "project.sqlite", read_only=True)
        except (OSError, sqlite3.Error, KeyError):
            log.warning(t("log.series.project_skipped", path=str(project)))
            continue
        try:
            out.extend(replace(p, project=project) for p in history.passages(person))
        finally:
            history.close()
    return out
