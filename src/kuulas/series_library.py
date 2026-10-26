"""The series library: one small JSON file per series (docs/design/SERIES.md).

``<config>/series/<id>.json`` (``$KUULAS_SERIES_DIR`` in tests), next to the user's
other per-user files: the series is the user's, not one project's, and a project
keeps its own copy of what it got (``Project.series``), so the project still opens
and works when the file is missing or on another Mac.

A record::

    {"format": "kuulas-series", "version": 1, "id": "<uuid7>", "name": "...",
     "updated_utc": "...", "settings": {...},          # series_settings sections
     "music": {"entries": [clipboard entry, ...]},     # clipboard.json's entry format
     "media": {"<sha256>": {"name": "...", "paths": ["/abs/file", ...]}}}

``music`` holds the series' standing clips (intro, outro, beds) as clipboard
entries, references to recordings by SHA-256 and never audio, so the Clipboard's
later "series shelf" reads the same entries. ``media`` says where each recording
was found, for linking it in place (hash-checked, never copied or overwritten).

Only ``<id>.json`` is read: a sync tool's conflicted copy beside it is another
name and ignored. Unknown keys are kept on every write. Writes are atomic.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import db as dbm
from .messages import config_dir, t
from .ops import EditError
from .package import write_json_atomic
from .series_settings import normalise_settings

log = logging.getLogger("kuulas.series_library")

FORMAT = "kuulas-series"
VERSION = 1
MAX_NAME = 100
#: A series file is settings and references; anything larger is not one of ours.
MAX_BYTES = 4_000_000
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class SeriesLibraryError(EditError):
    """A series id, name or record the library cannot take."""


def default_folder() -> Path:
    override = os.environ.get("KUULAS_SERIES_DIR")
    return Path(override) if override else config_dir() / "series"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_name(name: object) -> str:
    text = name.strip() if isinstance(name, str) else ""
    if not text or len(text) > MAX_NAME or "\0" in text:
        raise SeriesLibraryError("error.series.bad_name")
    return text


class SeriesLibrary:
    def __init__(self, folder: str | Path | None = None) -> None:
        self.folder = Path(folder) if folder is not None else default_folder()

    def _path(self, series_id: object) -> Path:
        if not isinstance(series_id, str) or not _ID.fullmatch(series_id):
            raise SeriesLibraryError("error.series.bad_series_id",
                                     series_id=str(series_id)[:80])
        base_dir = os.path.realpath(self.folder)
        fullpath = os.path.normpath(os.path.join(base_dir, f"{series_id}.json"))
        if not fullpath.startswith(base_dir + os.sep):
            raise SeriesLibraryError("error.series.bad_series_id",
                                     series_id=str(series_id)[:80])
        return Path(fullpath)

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            if path.is_symlink() or path.stat().st_size > MAX_BYTES:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            return None
        if data.get("id") != path.stem or not isinstance(data.get("name"), str):
            return None
        return data

    def load(self, series_id: str) -> dict | None:
        """The record, or None when it is missing or unreadable (never an error)."""
        path = self._path(series_id)
        data = self._read(path)
        if data is None and path.exists():
            log.warning(t("log.series.damaged", path=str(path)))
        return data

    def list(self) -> list[dict]:
        """Every readable series, by name."""
        try:
            paths = sorted(self.folder.glob("*.json"))
        except OSError:
            return []
        records = [r for r in (self._read(p) for p in paths if _ID.fullmatch(p.stem))
                   if r is not None]
        return sorted(records, key=lambda r: (r["name"].casefold(), r["id"]))

    def _write(self, record: dict) -> dict:
        record["updated_utc"] = _now()
        self.folder.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self._path(record["id"]), record)
        return record

    def create(self, name: object, settings: dict, *,
               series_id: str | None = None) -> dict:
        """A new series (or, with ``series_id``, one whose file was lost: the
        project's copy brings it back under the same id)."""
        sid = series_id or dbm.uuid7()
        self._path(sid)
        record = {"format": FORMAT, "version": VERSION, "id": sid,
                  "name": _clean_name(name), "settings": normalise_settings(settings),
                  "music": {"entries": []}, "media": {}}
        return self._write(record)

    def update(self, series_id: str, *, name: object = None, settings: dict | None = None,
               music: dict | None = None, media: dict | None = None) -> dict:
        """Change what is given; everything else (also unknown keys) stays."""
        record = self.load(series_id)
        if record is None:
            raise SeriesLibraryError("error.series.missing", series_id=series_id)
        if name is not None:
            record["name"] = _clean_name(name)
        if settings is not None:
            record["settings"] = normalise_settings(settings)
        if music is not None:
            record["music"] = music
        if media is not None:
            record["media"] = media
        return self._write(record)


def entries_of(record: dict | None) -> list[Any]:
    """The music entries of a record as stored (a damaged list is empty)."""
    music = (record or {}).get("music")
    entries = music.get("entries") if isinstance(music, dict) else None
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def media_paths(record: dict | None, digest: str) -> list[str]:
    """Where the record says ``digest`` was found (a damaged entry is none)."""
    media = (record or {}).get("media")
    item = media.get(digest) if isinstance(media, dict) else None
    paths = item.get("paths") if isinstance(item, dict) else None
    return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []
