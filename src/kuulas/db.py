"""``project.sqlite``: the v1 schema, content-addressed blobs and step ids.

The schema is docs/FORMAT.md's. ``History`` (edits, material) and
``MediaStore`` (media rows) each open their own connection to the same
file; WAL lets them, and ``busy_timeout`` makes the second writer wait
instead of failing.

Nothing here drops a table or rewrites a row whole: a newer kuulas may have
added tables and columns, and they must survive this version's saves.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .messages import KuulasError

SCHEMA_VERSION = 3

SCHEMA = """
create table if not exists meta(key text primary key, value text not null);
create table if not exists blobs(
    hash text primary key, kind text not null, data blob not null);
create table if not exists media(
    id text primary key,
    sha256 text not null unique,
    name text not null,
    storage text not null,
    channels integer not null,
    source_rate integer not null,
    source_frames integer not null,
    subtype text,
    lossless integer not null,
    time_ref_flicks integer,
    linked_path text, linked_size integer, linked_mtime_ns integer,
    linked_package_rel text, linked_series_rel text,
    excerpt_of text, excerpt_start_flicks integer,
    tags text not null default '{}',
    extra text not null default '{}',
    added_utc text not null);
create table if not exists media_paths(
    sha256 text, path text, first_seen_utc text, last_seen_utc text,
    primary key (sha256, path));
create table if not exists material_revs(
    id integer primary key, parent integer, label text not null,
    root text not null references blobs(hash), created_utc text);
create table if not exists transcript_revs(
    id integer primary key, media text not null, parent integer,
    words text not null references blobs(hash),
    engine text not null, created_utc text);
create table if not exists edits(
    id text primary key, name text not null, created_utc text,
    archived integer not null default 0, head text);
create table if not exists nodes(
    id text primary key,
    edit text not null references edits(id),
    parent text,
    author text not null,
    machine text not null,
    label text not null,
    op text not null,
    state text not null references blobs(hash),
    material_from integer, material_to integer,
    context text,
    created_utc text not null);
create index if not exists nodes_by_parent on nodes(edit, parent);
create table if not exists checkpoints(
    node text primary key references nodes(id),
    name text not null,
    kind text not null,
    copy text,
    created_utc text not null);
"""

#: How long a writer waits for another connection's write to finish. Writes
#: are single small transactions; 10 s only ever matters on a stalled disk.
BUSY_TIMEOUT_MS = 10_000


class FormatError(KuulasError, RuntimeError):
    """The database is not one this version can use as it is."""


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    """A connection in autocommit mode; transactions are explicit (``tx``)."""
    path = Path(path)
    if read_only:
        db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True,
                             check_same_thread=False, isolation_level=None)
    else:
        db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    db.execute(f"pragma busy_timeout={BUSY_TIMEOUT_MS}")
    if not read_only:
        db.execute("pragma journal_mode=wal")
        # FULL: a commit is on disk before it returns.
        db.execute("pragma synchronous=full")
    return db


def checkpoint(db: sqlite3.Connection) -> None:
    """Fold the WAL into the main file and truncate it. A sync service uploads
    the side files independently, so a closed project should have none to
    speak of. Does nothing (not an error) while a reader still holds the log."""
    db.execute("pragma wal_checkpoint(truncate)").fetchall()


def tables(db: sqlite3.Connection) -> set[str]:
    return {r[0] for r in db.execute("select name from sqlite_master where type='table'")}


def is_v0(db: sqlite3.Connection) -> bool:
    """A database written before v1: integer node ids, no ``edits`` table."""
    names = tables(db)
    return "nodes" in names and "edits" not in names


def ensure_schema(db: sqlite3.Connection, rate: int) -> None:
    """Create the v1 tables that are missing. Refuses a v0 database: that
    needs ``migrations.migrate_0_to_1`` first, with its backup."""
    if is_v0(db):
        raise FormatError("error.package.needs_migration")
    with tx(db):
        create_tables(db)
        db.execute("insert or ignore into meta(key, value) values ('schema_version', ?)",
                   (str(SCHEMA_VERSION),))
        db.execute("insert or ignore into meta(key, value) values ('project_rate', ?)",
                   (str(int(rate)),))


def create_tables(db: sqlite3.Connection) -> None:
    """The v1 tables and indexes that are missing, inside the caller's transaction."""
    for statement in SCHEMA.split(";"):
        if statement.strip():
            db.execute(statement)
    columns = {row[1] for row in db.execute("pragma table_info(media)")}
    for name in ("linked_package_rel", "linked_series_rel"):
        if name not in columns:
            db.execute(f"alter table media add column {name} text")
    set_meta(db, "schema_version", str(SCHEMA_VERSION))


def meta(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute("select value from meta where key=?", (key,)).fetchone()
    return None if row is None else row[0]


def set_meta(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute("insert or replace into meta(key, value) values (?, ?)", (key, value))


@contextmanager
def tx(db: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One write transaction, taken up front so two writers never deadlock."""
    if db.in_transaction:
        yield db  # nested: the outer transaction commits
        return
    db.execute("begin immediate")
    try:
        yield db
    except BaseException:
        db.execute("rollback")
        raise
    db.execute("commit")


# -- content-addressed blobs ---------------------------------------------------


def canonical(obj: Any) -> bytes:
    """The one byte form of a JSON value, so equal states hash equal."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode()


def pack(obj: Any) -> tuple[str, bytes]:
    """``(sha256 of the canonical JSON, zlib level 6 of it)``."""
    raw = canonical(obj)
    return hashlib.sha256(raw).hexdigest(), zlib.compress(raw, 6)


def put_blob(db: sqlite3.Connection, kind: str, obj: Any) -> str:
    digest, data = pack(obj)
    db.execute("insert or ignore into blobs(hash, kind, data) values (?, ?, ?)",
               (digest, kind, data))
    return digest


def get_blob(db: sqlite3.Connection, digest: str) -> Any:
    row = db.execute("select data from blobs where hash=?", (digest,)).fetchone()
    if row is None:
        raise KeyError(digest)
    return json.loads(zlib.decompress(row[0]))


# -- step ids ------------------------------------------------------------------

_SEQ_MAX = 0xFFF


class Uuid7Clock:
    """UUIDv7s (RFC 9562): 48-bit Unix milliseconds, a counter, randomness.

    Unique across copies of a project, so steps made apart can be merged
    (docs/FORMAT.md, "Review round trips"). Monotonic per clock: within one
    millisecond the 12-bit ``rand_a`` field counts up, so sorting ids gives
    the order they were made in.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_ms = 0
        self._seq = 0

    def next(self, ms: int | None = None) -> str:
        """An id for now, or for ``ms`` (a migrated step's own time)."""
        with self._lock:
            now = int(time.time() * 1000) if ms is None else int(ms)
            if now <= self._last_ms:
                now, seq = self._last_ms, self._seq + 1
                if seq > _SEQ_MAX:
                    now, seq = now + 1, 0
            else:
                # Start low in the counter so a burst in one millisecond has room.
                seq = secrets.randbelow(_SEQ_MAX // 2)
            self._last_ms, self._seq = now, seq
        value = ((now & ((1 << 48) - 1)) << 80) | (0x7 << 76) | (seq << 64)
        value |= (0b10 << 62) | secrets.randbits(62)
        return str(uuid.UUID(int=value))


_clock = Uuid7Clock()


def uuid7() -> str:
    """A new step id, ordered after every id this process made before."""
    return _clock.next()
