"""Undo tree and crash safety in one SQLite file.

Every edit is a node holding the *whole* resulting project state, written
and fsynced before the edit is acknowledged. So:

* A crash loses nothing that was on screen: reopening resumes at the last
  committed node.
* Undo never destroys: an edit after undo starts a new branch, and every
  earlier state stays reachable with ``goto``.
* Replaying needs no code: states are stored, not recomputed, so a change
  to an edit's code cannot rewrite old history.

Transcripts are large and change rarely, so they are stored once per
revision and the project state refers to them by id.
"""

from __future__ import annotations

import json
import sqlite3
import time
import zlib
from pathlib import Path

from .model import Project

SCHEMA = """
create table if not exists nodes (
    id integer primary key,
    parent integer references nodes(id),
    label text not null,
    state blob not null,
    created real not null
);
create table if not exists meta (key text primary key, value text not null);
create table if not exists transcripts (
    id integer primary key,
    media text not null,
    words blob not null,
    created real not null
);
"""


def _pack(p: Project) -> bytes:
    return zlib.compress(p.to_json().encode(), 6)


def _unpack(blob: bytes) -> Project:
    return Project.from_json(zlib.decompress(blob).decode())


class History:
    def __init__(self, path: str | Path, initial: Project | None = None):
        self.path = Path(path)
        self.db = sqlite3.connect(self.path, check_same_thread=False,
                                  isolation_level=None)
        self.db.execute("pragma journal_mode=wal")
        # FULL: the commit is on disk before ``commit`` returns.
        self.db.execute("pragma synchronous=full")
        self.db.executescript(SCHEMA)
        self._coalesce: str | None = None
        row = self.db.execute("select value from meta where key='head'").fetchone()
        if row is None:
            self.head = self._insert(None, "new project", initial or Project())
            self._set_head(self.head)
        else:
            self.head = int(row[0])
        self.state = self._load(self.head)

    # -- storage ---------------------------------------------------------

    def _insert(self, parent: int | None, label: str, state: Project) -> int:
        cur = self.db.execute(
            "insert into nodes(parent, label, state, created) values (?,?,?,?)",
            (parent, label, _pack(state), time.time()))
        return int(cur.lastrowid)

    def _set_head(self, node: int) -> None:
        self.db.execute("insert or replace into meta(key, value) values ('head', ?)",
                        (str(node),))

    def _load(self, node: int) -> Project:
        row = self.db.execute("select state from nodes where id=?", (node,)).fetchone()
        if row is None:
            raise KeyError(node)
        return _unpack(row[0])

    def _parent(self, node: int) -> int | None:
        row = self.db.execute("select parent from nodes where id=?", (node,)).fetchone()
        return None if row is None else row[0]

    def _children(self, node: int) -> list[int]:
        rows = self.db.execute(
            "select id from nodes where parent=? order by id", (node,)).fetchall()
        return [r[0] for r in rows]

    # -- edits -----------------------------------------------------------

    def commit(self, label: str, state: Project, coalesce: str | None = None) -> None:
        """Record ``state`` as the result of an edit.

        ``coalesce``: consecutive commits with the same key (one slider drag,
        one nudge run) replace each other, so they undo as one step. Any
        undo/redo/goto, or an edit with another key, ends the run.
        """
        with self.db:
            if coalesce is not None and coalesce == self._coalesce:
                self.db.execute("update nodes set label=?, state=?, created=? where id=?",
                                (label, _pack(state), time.time(), self.head))
            else:
                self.head = self._insert(self.head, label, state)
                self._set_head(self.head)
        self._coalesce = coalesce
        self.state = state

    def _move(self, node: int) -> None:
        state = self._load(node)
        with self.db:
            self._set_head(node)
        self.head, self.state, self._coalesce = node, state, None

    @property
    def can_undo(self) -> bool:
        return self._parent(self.head) is not None

    @property
    def can_redo(self) -> bool:
        return bool(self._children(self.head))

    def undo(self) -> bool:
        parent = self._parent(self.head)
        if parent is None:
            return False
        self._move(parent)
        return True

    def redo(self) -> bool:
        children = self._children(self.head)
        if not children:
            return False
        self._move(children[-1])
        return True

    def goto(self, node: int) -> None:
        self._move(int(node))

    def nodes(self) -> list[dict]:
        rows = self.db.execute(
            "select id, parent, label, created from nodes order by id").fetchall()
        return [{"id": i, "parent": p, "label": lab, "created": c}
                for i, p, lab, c in rows]

    # -- transcripts -----------------------------------------------------

    def add_transcript(self, media_id: str, words: list[dict]) -> int:
        blob = zlib.compress(json.dumps(words, separators=(",", ":")).encode(), 6)
        with self.db:
            cur = self.db.execute(
                "insert into transcripts(media, words, created) values (?,?,?)",
                (media_id, blob, time.time()))
        return int(cur.lastrowid)

    def transcript(self, rev: int) -> list[dict]:
        row = self.db.execute("select words from transcripts where id=?",
                              (rev,)).fetchone()
        if row is None:
            raise KeyError(rev)
        return json.loads(zlib.decompress(row[0]))

    def close(self) -> None:
        self.db.close()
