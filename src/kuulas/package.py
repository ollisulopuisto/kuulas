"""``Name.kuulas``: the project package (docs/FORMAT.md).

A folder holding ``manifest.json`` (what format this is), ``project.sqlite``
(all state), ``lock.json`` (who has it open), the media, rebuildable
``caches/`` and automatic ``backups/``. This module creates and opens one:

* **Reader rules.** A ``min_reader`` above ours refuses to open, naming the
  version that wrote it; a ``version`` above ours opens normally, and what
  it does not understand is carried through saves.
* **One writer.** A fresh lock held by another host or process opens the
  project read-only. Two machines writing one ``project.sqlite`` through a
  sync service corrupt it, and the owner works on a Mac and a Windows PC.
* **Migrations** run after a backup, then the manifest is rewritten.
* **Backups** every 10 minutes while there are changes, by SQLite's online
  backup API, never by touching the live file.

The manifest is written once at create and on upgrade only (temp file,
fsync, rename), and last on create, so a half-made package is never taken
for a finished one.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import threading
from datetime import UTC, datetime, timedelta, tzinfo
from importlib import metadata
from pathlib import Path
from typing import Any

from . import db as dbm
from . import migrations
from .clock import RateError, check_rate
from .history import History
from .media import MediaStore
from .messages import KuulasError, t
from .model import Project

log = logging.getLogger("kuulas.package")

FORMAT_NAME = "kuulas-project"
#: The format this code writes. Rises with every format change.
VERSION = 2
#: The newest ``min_reader`` this code can read.
READER = 1

#: The lock is rewritten this often while the project is open...
HEARTBEAT_S = 30
#: ...and a lock whose heartbeat is older than this was left by a crash.
#: Four missed heartbeats: a sleeping laptop or a slow sync must not make a
#: live project look abandoned.
STALE_S = 120
#: Automatic backup interval, while there are changes to back up.
BACKUP_EVERY_S = 600
#: Kept: the newest 12 automatic backups (two hours of work)...
KEEP_RECENT = 12
#: ...plus the newest of each of the last 14 days.
KEEP_DAYS = 14

DIRS = ("media", "media/excerpts", "media/originals", "caches/peaks", "caches/onsets",
        "caches/analysis", "caches/render", "backups", "recordings")

_STAMP = "%Y%m%dT%H%M%SZ"
_AUTO = re.compile(r"^auto-(\d{8}T\d{6}Z)\.sqlite$")


class PackageError(KuulasError, RuntimeError):
    """The folder cannot be opened or created as a kuulas project."""


def kuulas_version() -> str:
    try:
        return metadata.version("kuulas")
    except metadata.PackageNotFoundError:
        return "unknown"


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def write_json_atomic(path: Path, data: dict) -> None:
    """Temp file, fsync, rename: the old file or the new one, never half."""
    # The token keeps two threads writing one file from sharing a temp file.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    if hasattr(os, "O_DIRECTORY"):  # POSIX: make the rename itself durable
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_manifest(folder: str | Path, data: dict) -> None:
    write_json_atomic(Path(folder) / "manifest.json", data)


def read_manifest(folder: str | Path) -> dict | None:
    try:
        return json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _new_manifest(project_id: str, created_utc: str) -> dict:
    return {"format": FORMAT_NAME, "version": VERSION, "min_reader": READER,
            "created_utc": created_utc, "written_by": f"kuulas {kuulas_version()}",
            "id": project_id, "copy": secrets.token_hex(16), "lineage": []}


# -- lock ------------------------------------------------------------------------


def _me() -> dict:
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = ""
    return {"host": socket.gethostname(), "pid": os.getpid(), "user": user}


def _read_lock(folder: Path) -> dict | None:
    try:
        lock = json.loads((folder / "lock.json").read_text(encoding="utf-8"))
        _parse_iso(lock["heartbeat_utc"])
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError):
        # Unreadable (a crash mid-write, a sync conflict copy): nobody's.
        return {"host": "?", "pid": None, "heartbeat_utc": "1970-01-01T00:00:00Z"}
    return lock


def _is_mine(lock: dict) -> bool:
    me = _me()
    return lock.get("host") == me["host"] and lock.get("pid") == me["pid"]


def _write_lock(folder: Path, now: datetime, opened: str | None = None) -> None:
    write_json_atomic(folder / "lock.json",
                      {**_me(), "opened_utc": opened or _iso(now),
                       "heartbeat_utc": _iso(now)})


def _lock_holder(folder: Path, now: datetime) -> dict | None:
    """The live lock of another host or process, if there is one.

    A stale one is taken over (with a warning) by returning None.
    """
    lock = _read_lock(folder)
    if lock is None or _is_mine(lock):
        return None
    age = (now - _parse_iso(lock["heartbeat_utc"])).total_seconds()
    if age < STALE_S:
        return lock
    log.warning(t("log.package.stale_lock", host=lock.get("host", "?"),
                  heartbeat=lock["heartbeat_utc"]))
    return None


# -- backups ---------------------------------------------------------------------


def prune_backups(folder: str | Path, now: datetime | None = None,
                  tz: tzinfo | None = None) -> list[Path]:
    """Delete automatic backups the retention rule does not keep; returns them.

    Kept: the newest ``KEEP_RECENT``, and the newest of each of the last
    ``KEEP_DAYS`` days (today included). Days are in ``tz``, by default
    this computer's own time zone, so "a day" is the owner's day. Other
    files (pre-migration copies) are never touched.
    """
    now = now or datetime.now(UTC)
    tz = tz or datetime.now().astimezone().tzinfo
    found = []
    for path in Path(folder).iterdir():
        m = _AUTO.match(path.name)
        if m:
            found.append((datetime.strptime(m[1], _STAMP).replace(tzinfo=UTC), path))
    found.sort(reverse=True)
    keep = {p for _, p in found[:KEEP_RECENT]}
    today = now.astimezone(tz).date()
    days = {today - timedelta(days=d) for d in range(KEEP_DAYS)}
    for when, path in found:  # newest first: the first seen of a day is its last
        day = when.astimezone(tz).date()
        if day in days:
            keep.add(path)
            days.discard(day)
    removed = [p for _, p in found if p not in keep]
    for path in removed:
        path.unlink(missing_ok=True)
    return removed


def backup_to(db_path: Path, target: Path) -> Path:
    """A consistent copy of the database by the online backup API, read
    through its own read-only connection: the live file is never written."""
    partial = target.with_name(target.name + ".partial")
    source = dbm.connect(db_path, read_only=True)
    copy = sqlite3.connect(partial)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    partial.replace(target)
    return target


# -- the package -----------------------------------------------------------------


class Package:
    """An open project: its ``history``, its media ``store``, the lock and backups."""

    def __init__(self, folder: Path, manifest: dict, *, locked_by: dict | None,
                 author: str | None = None):
        self.path = folder
        self.manifest = manifest
        self.locked_by = locked_by
        self.read_only = locked_by is not None
        self.db_path = folder / "project.sqlite"
        host = locked_by.get("host") if locked_by else None
        self.history = History(self.db_path, author=author, read_only=self.read_only,
                               locked_by=host)
        self.store = MediaStore(folder / "media", self.history.rate, db=self.db_path,
                                cache_root=folder / "caches", read_only=self.read_only,
                                package_root=folder)
        now = datetime.now(UTC)
        self._opened = _iso(now)
        self._last_beat = self._last_backup = now
        self._backed_up = self._changes()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        size = self.db_path.stat().st_size
        log.info(t("log.package.opened", path=str(folder), size_mb=round(size / 1e6, 1)))

    def _changes(self) -> int:
        """Rows written by this session, through either connection."""
        return self.history.db.total_changes + self.store.db.total_changes

    # -- timers ------------------------------------------------------------

    def heartbeat(self, now: datetime | None = None) -> None:
        if self.read_only:
            return
        now = now or datetime.now(UTC)
        _write_lock(self.path, now, self._opened)
        self._last_beat = now

    def backup(self, now: datetime | None = None) -> Path:
        now = now or datetime.now(UTC)
        changes = self._changes()
        stamp = now.astimezone(UTC).strftime(_STAMP)
        target = self.path / "backups" / f"auto-{stamp}.sqlite"
        target.parent.mkdir(exist_ok=True)
        backup_to(self.db_path, target)
        self._last_backup, self._backed_up = now, changes
        prune_backups(target.parent, now)
        return target

    def tick(self, now: datetime | None = None) -> Path | None:
        """Heartbeat when due; back up when due and there are changes.

        Returns the backup made, if any. ``start`` calls this on a timer.
        """
        if self.read_only:
            return None
        now = now or datetime.now(UTC)
        if (now - self._last_beat).total_seconds() >= HEARTBEAT_S:
            self.heartbeat(now)
        due = (now - self._last_backup).total_seconds() >= BACKUP_EVERY_S
        if due and self._changes() != self._backed_up:
            return self.backup(now)
        return None

    def start(self) -> None:
        """Run ``tick`` every ``HEARTBEAT_S`` seconds until ``close``."""
        def loop() -> None:
            while not self._stop.wait(HEARTBEAT_S):
                try:
                    self.tick()
                except (OSError, sqlite3.Error) as e:
                    # A full disk or a busy database must not kill the timer:
                    # the next tick tries again.
                    log.warning(t("log.package.tick_failed", error=str(e)))
        self._thread = threading.Thread(target=loop, name="kuulas-package", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.history.close()
        self.store.close()
        if not self.read_only:
            lock = _read_lock(self.path)
            if lock is not None and _is_mine(lock):
                (self.path / "lock.json").unlink(missing_ok=True)


def create(path: str | Path, rate: int = Project().rate, *,
           author: str | None = None) -> Package:
    """A new, empty project at ``path`` (conventionally ``Name.kuulas``)."""
    folder = Path(path)
    try:
        check_rate(rate)
    except RateError as e:
        raise PackageError(e.key, **e.params) from None
    if (folder / "manifest.json").exists() or (folder / "project.sqlite").exists():
        raise PackageError("error.package.exists", path=str(folder))
    for name in DIRS:
        (folder / name).mkdir(parents=True, exist_ok=True)
    project_id = secrets.token_hex(16)
    now = datetime.now(UTC)
    History(folder / "project.sqlite", Project(rate=rate)).close()
    db = dbm.connect(folder / "project.sqlite")
    with dbm.tx(db):
        dbm.set_meta(db, "project_id", project_id)
        dbm.set_meta(db, "created_utc", _iso(now))
    db.close()
    _write_lock(folder, now)
    write_manifest(folder, _new_manifest(project_id, _iso(now)))
    return Package(folder, read_manifest(folder) or {}, locked_by=None, author=author)


def open_package(path: str | Path, *, author: str | None = None) -> Package:
    """Open a project, migrating an older format after a backup.

    Read-only when another live host or process holds the lock.
    """
    folder = Path(path)
    if not folder.is_dir():
        raise PackageError("error.package.not_found", path=str(folder))
    manifest = read_manifest(folder)
    if manifest is None and not (folder / "project.sqlite").exists():
        raise PackageError("error.package.not_a_project", path=str(folder))
    if manifest is not None:
        if manifest.get("format") != FORMAT_NAME:
            raise PackageError("error.package.not_a_project", path=str(folder))
        if int(manifest.get("min_reader", 1)) > READER:
            raise PackageError("error.package.too_new",
                               written_by=manifest.get("written_by", "?"))
    now = datetime.now(UTC)
    holder = _lock_holder(folder, now)
    if holder is not None:
        log.info(t("log.package.read_only", host=holder.get("host", "?")))
    behind = manifest is None or int(manifest.get("version", 0)) < VERSION
    if behind and holder is not None:
        raise PackageError("error.package.upgrade_locked", host=holder.get("host", "?"))
    if holder is None:
        _write_lock(folder, now)
    try:
        if behind:
            manifest = _upgrade(folder, manifest)
        return Package(folder, manifest or {}, locked_by=holder, author=author)
    except BaseException:
        if holder is None:
            (folder / "lock.json").unlink(missing_ok=True)
        raise


def _upgrade(folder: Path, manifest: dict | None) -> dict:
    for name in DIRS:
        (folder / name).mkdir(parents=True, exist_ok=True)
    db = dbm.connect(folder / "project.sqlite")
    try:
        if manifest is not None:
            version = int(manifest.get("version", 0))
        elif dbm.is_v0(db):
            version = 0
        else:
            # A v1 database without a manifest: a crash after the migration
            # (or a create) and before the manifest. Finish the file steps.
            version = VERSION
            migrations.finish_v1(db, folder)
        migrations.upgrade(db, folder, version, VERSION)
        project_id = dbm.meta(db, "project_id")
        if project_id is None:
            project_id = secrets.token_hex(16)
            with dbm.tx(db):
                dbm.set_meta(db, "project_id", project_id)
        created = dbm.meta(db, "created_utc") or _iso(datetime.now(UTC))
    finally:
        db.close()
    new = {**(manifest or {}), **_new_manifest(project_id, created)}
    if manifest is not None:
        # An upgrade keeps the project's identity and hand-off lineage.
        for key in ("id", "copy", "lineage", "created_utc"):
            if key in manifest:
                new[key] = manifest[key]
    write_manifest(folder, new)
    migrations.cleanup_v0(folder)
    return new


# -- info --------------------------------------------------------------------------


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def info(path: str | Path) -> dict[str, Any]:
    """What ``kuulas info`` prints. Reads only: no lock, no migration."""
    folder = Path(path)
    manifest = read_manifest(folder)
    if manifest is None or manifest.get("format") != FORMAT_NAME:
        raise PackageError("error.package.not_a_project", path=str(folder))
    db_path = folder / "project.sqlite"
    sizes = {name: _size(folder / name) if (folder / name).exists() else 0
             for name in ("project.sqlite", "media", "caches", "backups")}
    db = dbm.connect(db_path, read_only=True)
    rate = int(dbm.meta(db, "project_rate") or Project().rate)
    db.close()
    store = MediaStore(folder / "media", rate, db=db_path,
                       cache_root=folder / "caches", read_only=True,
                       package_root=folder)
    try:
        missing = set(store.missing())
        counts = {"linked": 0, "working": 0, "excerpt": 0, "missing": len(missing)}
        for media_id in store.ids():
            if media_id not in missing:
                storage = store.meta(media_id)["storage"]
                counts[storage] = counts.get(storage, 0) + 1
    finally:
        store.close()
    backups = len(list((folder / "backups").glob("auto-*.sqlite")))
    return {"manifest": manifest, "sizes": sizes, "media": counts, "backups": backups}
