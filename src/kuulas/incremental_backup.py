"""Content-addressed backup chunks; project databases and media are never modified.

A reference is published only after all its chunks are committed with SQLite's
FULL synchronous setting. References are independent: none depends on an earlier
reference, but all require their sibling repository. The package's backup lock
serializes publication and collection; the live project's single-writer lock
also rules out a second process collecting this repository while we publish.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import zlib
from pathlib import Path

from . import db as dbm
from . import priority
from .messages import KuulasError

REPOSITORY = "incremental.sqlite"
SUFFIX = ".kbackup"
FORMAT = "kuulas-backup-chunks-v1"
#: Sixteen ordinary SQLite pages: bounded decompression and cheap changed chunks.
CHUNK = 65536
MAX_MANIFEST = 16 * 1024 * 1024


class BackupDataError(KuulasError, ValueError):
    """A damaged or unsafe incremental-backup component."""


def _sync_dir(folder: Path) -> None:
    if hasattr(os, "O_DIRECTORY"):
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def snapshot(source: Path, target: Path,
             cancel: threading.Event | None = None, *, quiet: bool = False,
             cooperative: bool = True) -> Path:
    """Online copy, yielding every 64 SQLite pages; unique partial, then rename."""
    partial = target.with_name(f"{target.name}.{secrets.token_hex(8)}.partial")
    def checkpoint() -> None:
        if quiet and priority.GATE.interactive():
            raise priority.CancelledError
        if cooperative and (priority.is_background() or cancel is not None):
            priority.checkpoint(cancel)

    try:
        checkpoint()
        # Reserve the path exclusively before handing it to SQLite.
        with partial.open("xb"):
            pass
        source_db = dbm.connect(source, read_only=True)
        try:
            dest = sqlite3.connect(partial)
            try:
                def progress(_status: int, _remaining: int, _total: int) -> None:
                    checkpoint()
                source_db.backup(dest, pages=64, progress=progress, sleep=0.05)
            finally:
                dest.close()
        finally:
            source_db.close()
        with partial.open("r+b") as output:
            os.fsync(output.fileno())
        partial.replace(target)
        _sync_dir(target.parent)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _repository(folder: Path, *, read_only: bool = False) -> sqlite3.Connection:
    path = folder / REPOSITORY
    if path.is_symlink():
        raise BackupDataError("error.backup.repository_symlink")
    if read_only:
        return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    db = sqlite3.connect(path)
    try:
        db.execute("pragma auto_vacuum=incremental")
        db.execute("pragma synchronous=full")
        db.execute("create table if not exists chunks("
                   "hash text primary key, data blob not null) without rowid")
        db.commit()
    except BaseException:
        db.close()
        raise
    return db


def _manifest(path: Path) -> dict:
    if path.is_symlink():
        raise BackupDataError("error.backup.reference_symlink")
    if path.stat().st_size > MAX_MANIFEST:
        raise BackupDataError("error.backup.manifest_large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupDataError("error.backup.unknown_format")
    chunks = data.get("chunks")
    size = data.get("size")
    digest = data.get("sha256")
    if (not isinstance(chunks, list) or not chunks
            or not isinstance(size, int) or isinstance(size, bool)
            or size <= (len(chunks) - 1) * CHUNK or size > len(chunks) * CHUNK
            or not _is_hash(digest) or any(not _is_hash(h) for h in chunks)):
        raise BackupDataError("error.backup.invalid_manifest")
    return data


def _is_hash(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def write(source: Path, target: Path,
          cancel: threading.Event | None = None, *, quiet: bool = False) -> Path:
    """Append unseen chunks and publish a manifest after their durable commit."""
    token = secrets.token_hex(8)
    staged = target.with_name(f"{target.name}.{token}.snapshot.partial")
    partial = target.with_name(f"{target.name}.{token}.partial")
    try:
        snapshot(source, staged, cancel, quiet=quiet)
        db = _repository(target.parent)
        try:
            hashes = []
            digest = hashlib.sha256()
            size = 0
            with staged.open("rb") as original, db:
                while chunk := original.read(CHUNK):
                    if quiet and priority.GATE.interactive():
                        raise priority.CancelledError
                    priority.checkpoint(cancel)
                    key = hashlib.sha256(chunk).hexdigest()
                    hashes.append(key)
                    digest.update(chunk)
                    size += len(chunk)
                    present = db.execute(
                        "select data from chunks where hash=? and length(data)<=?",
                        (key, CHUNK + 1024)).fetchone()
                    if present is None:
                        db.execute("insert into chunks values (?, ?)",
                                   (key, zlib.compress(chunk)))
                    else:
                        _decode(present[0], key)
            manifest = {"format": FORMAT, "chunks": hashes,
                        "size": size, "sha256": digest.hexdigest()}
            encoded = json.dumps(manifest, separators=(",", ":"))
            if len(encoded) > MAX_MANIFEST:
                raise BackupDataError("error.backup.manifest_large")
            with partial.open("x", encoding="utf-8") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            priority.checkpoint(cancel)
            partial.replace(target)
            _sync_dir(target.parent)
        finally:
            db.close()
    finally:
        staged.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
    return target


def _decode(data: bytes, key: str) -> bytes:
    if not isinstance(data, bytes) or len(data) > CHUNK + 1024:
        raise BackupDataError("error.backup.chunk_invalid")
    decoder = zlib.decompressobj()
    chunk = decoder.decompress(data, CHUNK + 1)
    if (len(chunk) > CHUNK or not decoder.eof or decoder.unused_data
            or hashlib.sha256(chunk).hexdigest() != key):
        raise BackupDataError("error.backup.chunk_damaged")
    return chunk


def unpack(source: Path, target: Path) -> None:
    """Reconstruct bounded chunks and verify identity; caller publishes target."""
    manifest = _manifest(source)
    db = _repository(source.parent, read_only=True)
    try:
        digest = hashlib.sha256()
        size = 0
        with target.open("wb") as output:
            for key in manifest["chunks"]:
                priority.checkpoint()
                row = db.execute(
                    "select data from chunks where hash=? and length(data)<=?",
                    (key, CHUNK + 1024)).fetchone()
                if row is None:
                    raise BackupDataError("error.backup.chunk_missing")
                chunk = _decode(row[0], key)
                digest.update(chunk)
                size += len(chunk)
                output.write(chunk)
            if size != manifest["size"] or digest.hexdigest() != manifest["sha256"]:
                raise BackupDataError("error.backup.identity_mismatch")
            output.flush()
            os.fsync(output.fileno())
    finally:
        db.close()


def storage_bytes(paths: list[Path]) -> int:
    """Unique compressed content plus references, counted once across snapshots."""
    hashes = set()
    total = 0
    for path in paths:
        total += path.stat().st_size
        hashes.update(_manifest(path)["chunks"])
    if not paths:
        return 0
    db = _repository(paths[0].parent, read_only=True)
    try:
        for key in hashes:
            row = db.execute("select length(data) from chunks where hash=?",
                             (key,)).fetchone()
            if row is None:
                raise BackupDataError("error.backup.chunk_missing")
            total += row[0]
    finally:
        db.close()
    return total


def collect(folder: Path) -> bool:
    """Drop only chunks proven unreachable. Any invalid reference prevents GC."""
    if not (folder / REPOSITORY).exists():
        return True
    try:
        keep = set()
        for path in folder.glob(f"*{SUFFIX}"):
            keep.update(_manifest(path)["chunks"])
    except (OSError, ValueError, TypeError):
        return False
    db = _repository(folder)
    try:
        with db:
            db.execute("create temp table kept(hash text primary key)")
            db.executemany("insert into kept values (?)", ((key,) for key in keep))
            db.execute("delete from chunks where hash not in (select hash from kept)")
        # Return freed tail pages; interior pages are reused by later snapshots.
        db.execute("pragma incremental_vacuum")
    finally:
        db.close()
    return True
