"""Finding a pasted entry's recordings for another project (WP46, WP20 step 2).

A clipboard entry holds only media hashes. Pasting it into a project that lacks
a recording can still work when the recording is a file on disk that the
*source* project once saw: its ``project.sqlite`` remembers every path a hash
was imported from (``media_paths``). This module answers "which files might be
that recording"; the caller links one in place (no copy) after checking its
hash, so a file that changed or went away is never trusted. Excerpts (copying
a part of a recording the target cannot reach) are not done here.
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from .media import _sha256 as media_sha256


def candidate_paths(source_project: str, digest: str) -> list[Path]:
    """Files the source project imported ``digest`` from that still exist,
    newest first. Fails soft: an unreadable or missing source gives []."""
    if not source_project:
        return []
    db = Path(source_project) / "project.sqlite"
    if not db.is_file():
        return []
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
    except sqlite3.Error:
        return []
    try:
        with contextlib.closing(conn):
            rows = conn.execute(
                "select path from media_paths where sha256=?"
                " order by last_seen_utc desc, rowid desc", (digest,)).fetchall()
    except sqlite3.Error:
        return []
    return [p for p in (Path(r[0]) for r in rows) if p.is_file()]


def has_digest(path: Path, digest: str) -> bool:
    """Whether the file at ``path`` still has the SHA-256 ``digest``."""
    try:
        return media_sha256(path) == digest
    except OSError:
        return False
