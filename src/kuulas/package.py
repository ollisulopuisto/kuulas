"""``Name.kuulas``: the project package (docs/FORMAT.md).

A folder holding ``manifest.json`` (what format this is), ``project.sqlite``
(all state), ``locks/`` (who has it open), the media, rebuildable
``caches/`` and automatic ``backups/``. This module creates and opens one:

* **Reader rules.** A ``min_reader`` above ours refuses to open, naming the
  version that wrote it; a ``version`` above ours opens normally, and what
  it does not understand is carried through saves.
* **One writer.** A fresh lock held by another host or process opens the
  project read-only. Two machines writing one ``project.sqlite`` through a
  sync service corrupt it, and the owner works on a Mac Studio and a MacBook.
  Every open instance writes only its *own* file in ``locks/``, so a sync
  service never sees two machines change one file (no "conflicted copy").
* **Migrations** run after a backup, then the manifest is rewritten.
* **Backups** every 10 minutes while there are changes, by SQLite's online
  backup API, never by touching the live file; then xz-compressed in the
  background and kept by count and by a size budget (docs/FORMAT.md "Backups",
  docs/DISK.md).

The manifest is written once at create and on upgrade only (temp file,
fsync, rename), and last on create, so a half-made package is never taken
for a finished one.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import logging
import lzma
import os
import re
import secrets
import shutil
import socket
import sqlite3
import threading
from datetime import UTC, datetime, timedelta, tzinfo
from importlib import metadata
from pathlib import Path
from typing import Any

from . import db as dbm
from . import migrations, priority, syncmark
from .clock import RateError, check_rate
from .history import History
from .media import MediaStore
from .messages import KuulasError, settings_file, t
from .model import Project

log = logging.getLogger("kuulas.package")

FORMAT_NAME = "kuulas-project"
#: The format this code writes. Rises with every format change.
VERSION = 3
#: The newest ``min_reader`` this code can read: a manifest asking for more
#: is refused. Equal to ``VERSION``, since every format change this reader
#: knows is one it can read.
READER = 3
#: What a project asks of a reader until something in it needs more.
BASE_READER = 1
#: A project holding a gate (WP44, format version 3) asks for this. An old
#: reader would keep the field in ``extra`` and play the track ungated, which
#: is audible, so it must refuse instead of guessing.
GATE_READER = 3

#: The lock is rewritten this often while the project is open. A minute, not
#: 30 s: every write is sync traffic.
HEARTBEAT_S = 60
#: A lock of a process on this machine whose heartbeat is older than this was
#: left by a crash (a live pid with a silent lock: a hung or reused pid).
STALE_S = 120
#: A lock of another host is judged by what the sync service has delivered, so
#: it must allow for sync delay of minutes: five heartbeats. A sleeping laptop
#: or a slow upload must not make a live project look abandoned.
STALE_FOREIGN_S = 300
#: A stale lock this old is deleted. Younger ones are only ignored, so a
#: delete is never the first thing a sync service sees of a slow machine.
SWEEP_S = 3600
LOCKS_DIR = "locks"
#: Automatic backup interval, while there are changes to back up.
BACKUP_EVERY_S = 600
#: Kept: the newest 12 automatic backups (two hours of work)...
KEEP_RECENT = 12
#: ...plus the newest of each of the last 14 days.
KEEP_DAYS = 14
#: Automatic backups are stored xz-compressed (lzma preset 3). The history's
#: states are already zlib blobs, so gzip gains nothing (1.02x), while lzma's
#: 4 MiB window finds the neighbouring, nearly identical states: a synthetic
#: 106 MB project.sqlite went to 11.0 MB (9.7x) in 5.0 s and back in 0.6 s;
#: preset 6 gave 10.5x in 7.7 s, preset 1 6.1x in 3.4 s (M1 Max, 2026-10-20).
XZ = ".xz"
XZ_PRESET = 3
#: Compression reads this much between two playback checkpoints.
CHUNK = 1 << 20
#: The total size automatic backups may take, unless ``backup_budget_mb`` in
#: settings.json says otherwise (0: no limit). The count rules apply first.
BUDGET_MB = 300
#: Kept whatever the budget: the newest 2 backups...
BUDGET_KEEP_RECENT = 2
#: ...and the newest of each of the last 3 days.
BUDGET_KEEP_DAYS = 3
#: No backup while the disk has less free than this many times the database:
#: the copy itself takes one database's worth.
FREE_FACTOR = 2

DIRS = ("media", "media/excerpts", "media/originals", "caches/peaks", "caches/onsets",
        "caches/analysis", "caches/render", "backups", "recordings", LOCKS_DIR)

_STAMP = "%Y%m%dT%H%M%SZ"
_AUTO = re.compile(r"^auto-(\d{8}T\d{6}Z)\.sqlite(\.xz)?$")


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
    return {"format": FORMAT_NAME, "version": VERSION, "min_reader": BASE_READER,
            "created_utc": created_utc, "written_by": f"kuulas {kuulas_version()}",
            "id": project_id, "copy": secrets.token_hex(16), "lineage": []}


# -- lock ------------------------------------------------------------------------


def _hostname() -> str:
    return socket.gethostname()


def _me() -> dict:
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = ""
    return {"host": _hostname(), "pid": os.getpid(), "user": user}


def _is_conflict(name: str) -> bool:
    """A file a sync service renamed because two machines wrote it (Dropbox:
    "x (Olli's MacBook's conflicted copy 2026-10-18).json"). Never a lock."""
    return "conflicted copy" in name.lower()


def _own_lock_path(folder: Path, instance: str) -> Path:
    host = re.sub(r"[^A-Za-z0-9._-]+", "_", _hostname())[:40].strip("._-") or "host"
    return folder / LOCKS_DIR / f"{host}-{instance}.json"


def _read_lock(path: Path) -> dict | None:
    """A lock file's content, or None for anything that is not a lock: a
    half-synced file, a crash mid-write, a conflicted copy. Never raises."""
    if _is_conflict(path.name):
        return None
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
        _parse_iso(lock["heartbeat_utc"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return lock if isinstance(lock, dict) else None


def _all_locks(folder: Path) -> list[tuple[Path, dict]]:
    """Every readable lock: the per-instance files in ``locks/`` and the legacy
    shared ``lock.json`` (read for projects last opened by an older kuulas)."""
    try:
        files = sorted((folder / LOCKS_DIR).glob("*.json"))
    except OSError:
        files = []
    found = []
    for path in [folder / "lock.json", *files]:
        lock = _read_lock(path)
        if lock is not None:
            found.append((path, lock))
    return found


def _is_mine(lock: dict) -> bool:
    me = _me()
    return lock.get("host") == me["host"] and lock.get("pid") == me["pid"]


def _pid_alive(pid: object) -> bool:
    """Is process `pid` running on this machine? Unknown or odd pids count as alive,
    so a lock is only taken over early when we are sure its owner is gone."""
    if not isinstance(pid, int) or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def _write_lock(folder: Path, instance: str, now: datetime,
                opened: str | None = None) -> None:
    """Write this instance's own lock file, and nobody else's."""
    path = _own_lock_path(folder, instance)
    path.parent.mkdir(exist_ok=True)
    write_json_atomic(path, {**_me(), "instance": instance,
                             "opened_utc": opened or _iso(now),
                             "heartbeat_utc": _iso(now)})


def _remove_lock(folder: Path, instance: str) -> None:
    _own_lock_path(folder, instance).unlink(missing_ok=True)


def _lock_holder(folder: Path, now: datetime, instance: str = "") -> dict | None:
    """The live lock of another host or process, if there is one.

    Stale ones are ignored (with a warning); one that is dead for certain (its
    pid is gone, here) or over ``SWEEP_S`` old is also deleted, best-effort.
    """
    holder, holder_age = None, 0.0
    for path, lock in _all_locks(folder):
        if lock.get("instance") == instance:
            continue
        age = (now - _parse_iso(lock["heartbeat_utc"])).total_seconds()
        here = lock.get("host") == _hostname()
        # A lock of a process on this very machine that no longer runs is dead at
        # once: waiting two minutes for a crashed or killed window helps nobody.
        gone = here and not _pid_alive(lock.get("pid"))
        if age < (STALE_S if here else STALE_FOREIGN_S) and not gone:
            if holder is None or age < holder_age:
                holder, holder_age = lock, age
            continue
        log.warning(t("log.package.stale_lock", host=lock.get("host", "?"),
                      heartbeat=lock["heartbeat_utc"]))
        if gone or age > SWEEP_S:
            path.unlink(missing_ok=True)
    return holder


# -- backups ---------------------------------------------------------------------


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0  # gone while we looked (pruned or compressed meanwhile)


def auto_backups(folder: str | Path) -> list[tuple[datetime, list[Path]]]:
    """The automatic backups in ``folder``, newest first: one entry per stamp
    with its files (``.sqlite``, ``.sqlite.xz``, or both while it is being
    compressed). Nothing else in the folder is ever listed."""
    found: dict[datetime, list[Path]] = {}
    try:
        paths = sorted(Path(folder).iterdir())
    except OSError:
        return []
    for path in paths:
        m = _AUTO.match(path.name)
        if m:
            when = datetime.strptime(m[1], _STAMP).replace(tzinfo=UTC)
            found.setdefault(when, []).append(path)
    return sorted(found.items(), reverse=True)


def _best(paths: list[Path]) -> Path:
    """The file that stands for a backup: the compressed one when there is one."""
    return next((p for p in paths if p.name.endswith(XZ)), paths[0])


def _kept(stamps: list[datetime], recent: int, days: int, now: datetime,
          tz: tzinfo) -> set[datetime]:
    """The newest ``recent`` of ``stamps`` (newest first) and the newest of
    each of the last ``days`` days, today included, in ``tz``."""
    keep = set(stamps[:recent])
    today = now.astimezone(tz).date()
    wanted = {today - timedelta(days=d) for d in range(days)}
    for when in stamps:  # newest first: the first seen of a day is its last
        day = when.astimezone(tz).date()
        if day in wanted:
            keep.add(when)
            wanted.discard(day)
    return keep


def backup_budget_bytes() -> int:
    """``backup_budget_mb`` in settings.json, in bytes (0: no limit), else
    ``BUDGET_MB``. A damaged file or a value that is not a number >= 0 means
    the default, never an error."""
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    value = data.get("backup_budget_mb") if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        value = BUDGET_MB
    return int(value * 1_000_000)


def _mb(size: int) -> str:
    return f"{size / 1e6:.1f}"


def prune_backups(folder: str | Path, now: datetime | None = None,
                  tz: tzinfo | None = None, budget: int | None = None) -> list[Path]:
    """Delete automatic backups the retention rules do not keep; returns them.

    Kept: the newest ``KEEP_RECENT``, and the newest of each of the last
    ``KEEP_DAYS`` days (today included). Days are in ``tz``, by default
    this computer's own time zone, so "a day" is the owner's day. Then, with a
    ``budget`` (bytes; None or 0: none), the oldest kept ones go until the
    rest fit, except the newest ``BUDGET_KEEP_RECENT`` and the newest of each
    of the last ``BUDGET_KEEP_DAYS`` days, which stay even over the budget.
    Every deletion is logged with its size. Other files (pre-migration and
    pre-restore copies) are never touched.
    """
    now = now or datetime.now(UTC)
    tz = tz or datetime.now().astimezone().tzinfo
    found = auto_backups(folder)
    stamps = [when for when, _ in found]
    keep = _kept(stamps, KEEP_RECENT, KEEP_DAYS, now, tz)
    if budget:
        sizes = {when: sum(_file_size(p) for p in paths) for when, paths in found}
        protected = _kept(stamps, BUDGET_KEEP_RECENT, BUDGET_KEEP_DAYS, now, tz)
        total = sum(sizes[w] for w in keep)
        for when in reversed(stamps):  # oldest first
            if total <= budget:
                break
            if when in keep and when not in protected:
                keep.discard(when)
                total -= sizes[when]
        if total > budget:
            log.info(t("log.package.backup_over_budget", total_mb=_mb(total),
                       budget_mb=_mb(budget)))
    removed = []
    for when, paths in found:
        if when in keep:
            continue
        for path in paths:
            size = _file_size(path)
            path.unlink(missing_ok=True)
            removed.append(path)
            log.info(t("log.package.backup_pruned", name=path.name, size_mb=_mb(size)))
    return removed


def _fsync_dir(folder: Path) -> None:
    if hasattr(os, "O_DIRECTORY"):  # POSIX: make a rename itself durable
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _xz_digest(path: Path, cancel: threading.Event | None = None) -> str:
    """SHA-256 of what the xz file ``path`` decompresses to."""
    digest = hashlib.sha256()
    unpack = lzma.LZMADecompressor()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            priority.checkpoint(cancel)
            digest.update(unpack.decompress(chunk))
    if not unpack.eof:
        raise lzma.LZMAError(path.name)
    return digest.hexdigest()


class _MismatchError(Exception):
    """The compressed copy does not decompress to the original."""


def _compress_verified(src: Path, partial: Path, cancel: threading.Event | None) -> None:
    """Write ``src`` xz-compressed to ``partial``, fsync it, and read it back:
    ``_MismatchError`` unless it decompresses to exactly ``src``."""
    digest = hashlib.sha256()
    with src.open("rb") as f, partial.open("wb") as out:
        pack = lzma.LZMACompressor(preset=XZ_PRESET)
        while chunk := f.read(CHUNK):
            priority.checkpoint(cancel)
            digest.update(chunk)
            out.write(pack.compress(chunk))
        out.write(pack.flush())
        out.flush()
        os.fsync(out.fileno())
    if _xz_digest(partial, cancel) != digest.hexdigest():
        raise _MismatchError(src.name)


def compress_backup(src: Path, cancel: threading.Event | None = None) -> Path | None:
    """``auto-X.sqlite`` -> ``auto-X.sqlite.xz``: written under a temp name,
    fsynced, decompressed again and compared with the original, renamed, and
    only then is the original deleted. Waits while audio plays (on a background
    thread). Raises on failure, after removing its own temp file; the original
    is then still there. None when the original went away meanwhile (pruned)."""
    target = src.with_name(src.name + XZ)
    partial = target.with_name(f"{target.name}.{secrets.token_hex(4)}.partial")
    try:
        _compress_verified(src, partial, cancel)
        if not src.exists():
            partial.unlink(missing_ok=True)
            return None
        os.replace(partial, target)
        _fsync_dir(target.parent)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    src.unlink(missing_ok=True)
    _fsync_dir(target.parent)
    return target


def compress_pending(folder: str | Path,
                     cancel: threading.Event | None = None) -> list[Path]:
    """Compress every uncompressed automatic backup in ``folder``, newest
    first, one at a time. A failure keeps that original (logged) and moves on;
    ``priority.CancelledError`` stops the round."""
    done = []
    for _when, paths in auto_backups(folder):
        for src in paths:
            if src.name.endswith(XZ):
                continue
            try:
                made = compress_backup(src, cancel)
            except (OSError, lzma.LZMAError, _MismatchError) as e:
                log.warning(t("log.package.backup_compress_failed", name=src.name,
                              error=str(e) or type(e).__name__))
                continue
            if made is not None:
                log.info(t("log.package.backup_compressed", name=made.name,
                           size_mb=_mb(_file_size(made))))
                done.append(made)
    return done


def _unpack(src: Path, out_path: Path) -> None:
    """``src`` as a plain file at ``out_path`` (decompressed when it is xz), fsynced."""
    with src.open("rb") as f, out_path.open("wb") as out:
        unpack = lzma.LZMADecompressor() if src.name.endswith(XZ) else None
        while chunk := f.read(CHUNK):
            out.write(unpack.decompress(chunk) if unpack else chunk)
        if unpack is not None and not unpack.eof:
            raise lzma.LZMAError(src.name)
        out.flush()
        os.fsync(out.fileno())


def read_backup(src: Path, dest: Path) -> Path:
    """Copy the backup ``src`` (``.sqlite`` or ``.sqlite.xz``) to ``dest`` as a
    plain database: through a temp file, checked with ``integrity_check``, and
    only then renamed. ``PackageError`` for a damaged backup (``dest`` untouched)."""
    tmp = dest.with_name(f"{dest.name}.{secrets.token_hex(4)}.partial")
    try:
        _unpack(src, tmp)
        _check_database(tmp)
        os.replace(tmp, dest)
    except (OSError, lzma.LZMAError, EOFError, sqlite3.Error) as e:
        tmp.unlink(missing_ok=True)
        raise PackageError("error.package.backup_damaged", name=src.name,
                           error=str(e) or type(e).__name__) from None
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest


def _check_database(path: Path) -> None:
    """Raise ``sqlite3.Error`` unless ``path`` is an intact kuulas history."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        (result,) = db.execute("pragma integrity_check").fetchone()
        if result != "ok":
            raise sqlite3.DatabaseError(result)
        db.execute("select count(*) from nodes").fetchone()
    finally:
        db.close()


def restore_backup(folder: str | Path, backup: str | Path,
                   now: datetime | None = None) -> Path:
    """Make ``backup`` (a file name in ``backups/``, or a path; plain or xz)
    the project's database again. Only while nobody has the project open. The
    backup is decompressed and checked before anything changes; the current
    database is first copied to ``backups/pre-restore-<UTC>.sqlite`` (never
    pruned), which is returned. Media and recordings are never touched."""
    folder = Path(folder)
    now = now or datetime.now(UTC)
    src = Path(backup)
    if not src.is_absolute():
        src = folder / "backups" / src
    if not src.is_file():
        raise PackageError("error.package.not_found", path=str(src))
    for _path, lock in _all_locks(folder):
        age = (now - _parse_iso(lock["heartbeat_utc"])).total_seconds()
        if age < STALE_FOREIGN_S:
            raise PackageError("error.package.restore_open", host=lock.get("host", "?"))
    live = folder / "project.sqlite"
    staged = read_backup(src, folder / f"project.sqlite.restore-{secrets.token_hex(4)}")
    try:
        db = sqlite3.connect(live)
        try:
            db.execute("pragma wal_checkpoint(TRUNCATE)")
        finally:
            db.close()
        safety = backup_to(live, folder / "backups" /
                           f"pre-restore-{now.astimezone(UTC).strftime(_STAMP)}.sqlite")
        _check_database(safety)
        for suffix in ("-wal", "-shm"):
            live.with_name(live.name + suffix).unlink(missing_ok=True)
        os.replace(staged, live)
        _fsync_dir(folder)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    log.info(t("log.package.restored", name=src.name, safety=safety.name))
    return safety


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
    with partial.open("rb") as f:
        os.fsync(f.fileno())
    partial.replace(target)
    _fsync_dir(target.parent)
    return target


# -- the package -----------------------------------------------------------------


class Package:
    """An open project: its ``history``, its media ``store``, the lock and backups."""

    def __init__(self, folder: Path, manifest: dict, *, locked_by: dict | None,
                 author: str | None = None, instance: str = ""):
        self.path = folder
        self.instance = instance
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
        self._checkpointed = self._seen = self._backed_up
        self.history.on_gate = self._need_gate_reader
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # One background compressor at a time; a backup made while it runs
        # asks it for one more round instead of starting a second.
        self._compress_lock = threading.Lock()
        self._compressor: threading.Thread | None = None
        self._compress_again = False
        #: The backup this session made last (its plain name).
        self._made: Path | None = None
        if not self.read_only:
            syncmark.mark_package(folder)
        size = self.db_path.stat().st_size
        log.info(t("log.package.opened", path=str(folder), size_mb=round(size / 1e6, 1)))

    def _need_gate_reader(self) -> None:
        """Called by ``History`` before it writes a state that has a gate:
        the manifest asks for a reader that knows gates first, so a crash
        between the two leaves a stricter manifest, never a project an old
        reader would open and play wrongly. Never lowered again."""
        if int(self.manifest.get("min_reader", BASE_READER)) >= GATE_READER:
            return
        self.manifest = {**self.manifest, "min_reader": GATE_READER}
        write_manifest(self.path, self.manifest)

    def _changes(self) -> int:
        """Rows written by this session, through either connection."""
        return self.history.db.total_changes + self.store.db.total_changes

    # -- timers ------------------------------------------------------------

    def heartbeat(self, now: datetime | None = None) -> None:
        if self.read_only:
            return
        now = now or datetime.now(UTC)
        _write_lock(self.path, self.instance, now, self._opened)
        self._last_beat = now

    def checkpoint(self) -> None:
        """Fold the write-ahead logs into the main file and empty them, so a
        sync service never uploads a main file that lacks its latest edits."""
        if self.read_only:
            return
        for db in (self.history.db, self.store.db):
            try:
                dbm.checkpoint(db)
            except sqlite3.Error as e:
                # A reader holds the log open: the next quiet tick tries again.
                log.warning(t("log.package.tick_failed", error=str(e)))
                return
        self._checkpointed = self._changes()

    def backup(self, now: datetime | None = None) -> Path | None:
        """An automatic backup now: the online backup API to
        ``backups/auto-<UTC>.sqlite``, the count rules, then the background
        compressor (xz, then the size budget). Returns this session's last
        backup instead when nothing was written since it, and None (logged,
        not an error) when the disk has too little room for a copy."""
        now = now or datetime.now(UTC)
        changes = self._changes()
        folder = self.path / "backups"
        folder.mkdir(exist_ok=True)
        if changes == self._backed_up and (same := self._made_copy()) is not None:
            # Keyed on this session's own copy and its change counter: a backup
            # left by an earlier session may predate edits of a crash.
            self._last_backup = now
            prune_backups(folder, now)
            return same
        size = _file_size(self.db_path) + _file_size(
            self.db_path.with_name(self.db_path.name + "-wal"))
        free = shutil.disk_usage(folder).free
        if free < FREE_FACTOR * size:
            log.warning(t("log.package.backup_low_disk", free_mb=_mb(free),
                          size_mb=_mb(size)))
            self._last_backup = now  # try again at the next interval, not every tick
            return None
        stamp = now.astimezone(UTC).strftime(_STAMP)
        target = folder / f"auto-{stamp}.sqlite"
        backup_to(self.db_path, target)
        self._last_backup, self._backed_up, self._made = now, changes, target
        # The budget waits for the compressor: counted uncompressed, backups
        # that fit once compressed would be dropped.
        prune_backups(folder, now)
        self._kick_compressor()
        return target

    def _made_copy(self) -> Path | None:
        """This session's newest backup, compressed or not, if it is still there."""
        if self._made is None:
            return None
        for path in (self._made.with_name(self._made.name + XZ), self._made):
            if path.exists():
                return path
        return None

    def _kick_compressor(self) -> None:
        if self.read_only or self._stop.is_set():
            return
        with self._compress_lock:
            if self._compressor is not None:
                self._compress_again = True
                return
            self._compressor = priority.thread(self._compress_loop,
                                               "kuulas-backup-compress")
            self._compressor.start()

    def _compress_loop(self) -> None:
        """Compress the uncompressed automatic backups (new ones and those of
        older kuulas versions), then apply the budget; again while asked."""
        folder = self.path / "backups"
        while True:
            try:
                compress_pending(folder, self._stop)
                prune_backups(folder, budget=backup_budget_bytes())
            except priority.CancelledError:
                pass  # closing: an unfinished one stays uncompressed, for next time
            except (OSError, sqlite3.Error) as e:
                log.warning(t("log.package.tick_failed", error=str(e)))
            with self._compress_lock:
                if not self._compress_again or self._stop.is_set():
                    self._compressor = None
                    return
                self._compress_again = False

    def wait_compressed(self, timeout: float | None = None) -> None:
        """Wait for the background compressor to finish (tests, ``close``)."""
        while True:
            with self._compress_lock:
                worker = self._compressor
            if worker is None:
                return
            worker.join(timeout)
            if timeout is not None:
                return

    def tick(self, now: datetime | None = None) -> Path | None:
        """Heartbeat when due; back up when due and there are changes.

        Returns the backup made, if any. ``start`` calls this on a timer.
        """
        if self.read_only:
            return None
        now = now or datetime.now(UTC)
        if (now - self._last_beat).total_seconds() >= HEARTBEAT_S:
            self.heartbeat(now)
        # After a write burst: nothing written since the previous tick.
        changes = self._changes()
        if changes == self._seen and changes != self._checkpointed:
            self.checkpoint()
        self._seen = changes
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
        # Backups an older kuulas left uncompressed are compressed now, in the
        # background, one at a time.
        self._kick_compressor()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.wait_compressed()
        self.checkpoint()
        self.history.close()
        self.store.close()
        if not self.read_only:
            _remove_lock(self.path, self.instance)


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
    instance = secrets.token_hex(16)
    _write_lock(folder, instance, now)
    write_manifest(folder, _new_manifest(project_id, _iso(now)))
    return Package(folder, read_manifest(folder) or {}, locked_by=None, author=author,
                   instance=instance)


def open_package(path: str | Path, *, author: str | None = None,
                 now: datetime | None = None) -> Package:
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
    now = now or datetime.now(UTC)
    instance = secrets.token_hex(16)
    holder = _lock_holder(folder, now, instance)
    if holder is not None:
        log.info(t("log.package.read_only", host=holder.get("host", "?")))
    behind = manifest is None or int(manifest.get("version", 0)) < VERSION
    if behind and holder is not None:
        raise PackageError("error.package.upgrade_locked", host=holder.get("host", "?"))
    if holder is None:
        _write_lock(folder, instance, now)
    try:
        if behind:
            manifest = _upgrade(folder, manifest)
        return Package(folder, manifest or {}, locked_by=holder, author=author,
                       instance=instance)
    except BaseException:
        if holder is None:
            _remove_lock(folder, instance)
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
        # What the project already asks of a reader stays (a gate was written).
        new["min_reader"] = max(int(manifest.get("min_reader", BASE_READER)),
                                BASE_READER)
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
             for name in ("project.sqlite", "media", "caches", "backups", "recordings")}
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
    backups = len(auto_backups(folder / "backups"))
    return {"manifest": manifest, "sizes": sizes, "media": counts, "backups": backups}
