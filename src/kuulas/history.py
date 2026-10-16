"""Undo trees and crash safety, in ``project.sqlite`` (docs/FORMAT.md, v1).

Every edit is a node holding the *whole* resulting edit state, written and
fsynced before the edit is acknowledged. So:

* A crash loses nothing that was on screen: reopening resumes at the last
  committed node.
* Undo never destroys: an edit after undo starts a new branch, and every
  earlier state stays reachable with ``goto``.
* Replaying needs no code: states are stored, not recomputed, so a change
  to an edit's code cannot rewrite old history. The op that made a step is
  kept beside it as an audit trail only.

States are stored once each, by the hash of their canonical JSON, so undo,
redo and restore cycles cost nothing.

**Two kinds of state.** *Edit state* (tracks, clips, buses, master) belongs
to one edit; a project can hold several edits, each with its own tree.
*Material* (media rows, sync groups, transcripts, speaker names) is shared
by every edit. ``state`` puts the two together: the edit's tracks plus
every media row, the sync groups and the project rate. A commit whose state
has other sync groups than the material changes the material
(``ops.mark_in_sync``). Material is versioned too (``material_revs``): a
step that changed it records ``material_from`` and ``material_to``, and
undoing that step moves the material back, but only if nobody has changed
it since. Otherwise the undo is refused rather than silently throwing away
the later change.
"""

from __future__ import annotations

import getpass
import json
import socket
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import db as dbm
from .clock import flicks_to_frames, frames_to_flicks
from .messages import KuulasError, t
from .model import Media, Project, SyncGroup

#: The material root of a new project. Unknown keys a newer version adds
#: are kept, because roots are updated key by key, never rebuilt.
EMPTY_MATERIAL: dict[str, Any] = {"transcripts": {}, "speakers": {}, "sync": {}}

MAIN_EDIT = "main"


class HistoryError(KuulasError, RuntimeError):
    """The history cannot make this move; nothing changed."""


def edit_dict(p: Project) -> dict:
    """The part of ``p`` that belongs to one edit: everything but material."""
    d = p.to_dict()
    del d["media"], d["rate"], d["sync_groups"]
    return d


def sync_root(groups: tuple[SyncGroup, ...]) -> dict:
    """Sync groups as the material root holds them (docs/FORMAT.md):
    ``{group: {"main": media, "members": {media: origin_flicks}}}``."""
    out = {}
    for g in groups:
        d = g.to_dict()
        out[d.pop("id")] = d
    return out


def sync_groups(root: dict) -> tuple[SyncGroup, ...]:
    return tuple(SyncGroup.from_dict({**g, "id": gid})
                 for gid, g in sorted(root.get("sync", {}).items()))


def edit_blob(p: Project) -> tuple[str, bytes]:
    """``(hash, stored bytes)`` of ``p``'s edit state, as History keeps it."""
    return dbm.pack(edit_dict(p))


def default_author(db) -> str:
    """The person's name from the project settings, else the login name."""
    settings = json.loads(dbm.meta(db, "settings") or "{}")
    if settings.get("author"):
        return str(settings["author"])
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        # No login name (a service account, some containers): unnamed.
        return ""


def media_from_row(row: dict, rate: int) -> Media:
    frames = row["source_frames"]
    if row["source_rate"] != rate:
        frames = flicks_to_frames(frames_to_flicks(frames, row["source_rate"]), rate)
    return Media(id=row["id"], name=row["name"], channels=row["channels"],
                 frames=frames, sha256=row["sha256"],
                 time_ref_flicks=row["time_ref_flicks"], excerpt_of=row["excerpt_of"],
                 excerpt_start_flicks=row["excerpt_start_flicks"] or 0,
                 extra=json.loads(row["extra"] or "{}"))


def _rows(cursor) -> list[dict]:
    names = [c[0] for c in cursor.description]
    return [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]


class History:
    """One edit's undo tree, and the project's material.

    ``path`` is the ``project.sqlite`` file. ``edit`` picks which edit's
    tree this object moves in. ``read_only``: opened while another machine
    holds the lock (``package``); every write is refused.
    """

    def __init__(self, path: str | Path, initial: Project | None = None, *,
                 edit: str = MAIN_EDIT, author: str | None = None,
                 machine: str | None = None, read_only: bool = False,
                 locked_by: str | None = None):
        self.path = Path(path)
        self.read_only = read_only
        self.locked_by = locked_by
        self.db = dbm.connect(self.path, read_only=read_only)
        if not read_only:
            dbm.ensure_schema(self.db, (initial or Project()).rate)
        self.rate = int(dbm.meta(self.db, "project_rate") or Project().rate)
        self.author = default_author(self.db) if author is None else author
        self.machine = machine or socket.gethostname()
        self._coalesce: str | None = None
        #: Bumped on every write; ``package`` backs up when it has moved.
        self.generation = 0
        if not read_only and dbm.meta(self.db, "material_head") is None:
            self._create(initial or Project())
        self.edit = edit
        row = self.db.execute("select head from edits where id=?", (edit,)).fetchone()
        if row is None:
            raise HistoryError("error.history.no_edit", edit=edit)
        self.head: str = row[0]
        self._edit_state = self._load(self.head)
        self._composed: Project | None = None
        self._seen_version: int | None = None

    def _create(self, initial: Project) -> None:
        now = dbm.utc_now()
        with dbm.tx(self.db):
            root = dbm.put_blob(self.db, "material", EMPTY_MATERIAL)
            cur = self.db.execute(
                "insert into material_revs(parent, label, root, created_utc)"
                " values (null, 'new project', ?, ?)", (root, now))
            dbm.set_meta(self.db, "material_head", str(cur.lastrowid))
            self.db.execute("insert into edits(id, name, created_utc) values (?, ?, ?)",
                            (MAIN_EDIT, t("history.main_edit"), now))
            node = self._insert(MAIN_EDIT, None, "new project", initial)
            self.db.execute("update edits set head=? where id=?", (node, MAIN_EDIT))

    # -- storage ---------------------------------------------------------

    def _insert(self, edit: str, parent: str | None, label: str, state: Project, *,
                op: dict | None = None, context: Any = None,
                material: tuple[int, int] | None = None) -> str:
        node = dbm.uuid7()
        state_hash = dbm.put_blob(self.db, "edit-state", edit_dict(state))
        mf, mt = material or (None, None)
        self.db.execute(
            "insert into nodes(id, edit, parent, author, machine, label, op, state,"
            " material_from, material_to, context, created_utc)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (node, edit, parent, self.author, self.machine, label,
             json.dumps(op or {}), state_hash, mf, mt,
             None if context is None else json.dumps(context), dbm.utc_now()))
        return node

    def _node(self, node: str) -> dict:
        rows = _rows(self.db.execute("select * from nodes where id=?", (node,)))
        if not rows:
            raise KeyError(node)
        return rows[0]

    def _load(self, node: str) -> Project:
        d = dbm.get_blob(self.db, self._node(node)["state"])
        # Sync groups come from the material (an edit state written by
        # 26.10.16.5 still has its own; the material's win).
        return Project.from_dict({**d, "rate": self.rate, "sync_groups": []})

    def _parent(self, node: str) -> str | None:
        return self._node(node)["parent"]

    def _children(self, node: str) -> list[str]:
        rows = self.db.execute(
            "select id from nodes where edit=? and parent=? order by id",
            (self.edit, node)).fetchall()
        return [r[0] for r in rows]

    def _check_writable(self) -> None:
        if self.read_only:
            raise HistoryError("error.history.read_only", host=self.locked_by or "?")

    def _written(self) -> None:
        self.generation += 1
        self._composed = None

    # -- the composed state ------------------------------------------------

    def media_rows(self) -> list[dict]:
        return _rows(self.db.execute("select * from media order by added_utc, id"))

    @property
    def state(self) -> Project:
        """This edit's state with the material every edit shares (media rows).

        Rebuilt when any connection changed the database (an import by the
        media store, an edit in another window), so it is never stale.
        """
        version = self.db.execute("pragma data_version").fetchone()[0]
        if self._composed is None or version != self._seen_version:
            media = tuple(media_from_row(r, self.rate) for r in self.media_rows())
            self._composed = replace(self._edit_state, media=media,
                                     sync_groups=sync_groups(self.material))
            self._seen_version = version
        return self._composed

    # -- material ----------------------------------------------------------

    @property
    def material_head(self) -> int:
        return int(dbm.meta(self.db, "material_head") or 0)

    @property
    def material(self) -> dict:
        """The current material root: transcript per media, speaker names."""
        row = self.db.execute("select root from material_revs where id=?",
                              (self.material_head,)).fetchone()
        return {**EMPTY_MATERIAL, **dbm.get_blob(self.db, row[0])}

    def _material_rev(self, root: dict, label: str) -> tuple[int, int]:
        """A new material revision after the current head; ``(from, to)``."""
        before = self.material_head
        digest = dbm.put_blob(self.db, "material", root)
        cur = self.db.execute(
            "insert into material_revs(parent, label, root, created_utc)"
            " values (?,?,?,?)",
            (before, label, digest, dbm.utc_now()))
        after = int(cur.lastrowid)
        dbm.set_meta(self.db, "material_head", str(after))
        return before, after

    # -- edits -----------------------------------------------------------

    def commit(self, label: str, state: Project, coalesce: str | None = None, *,
               op: dict | None = None, context: Any = None,
               material: dict | None = None) -> None:
        """Record ``state`` as the result of an edit.

        ``coalesce``: consecutive commits with the same key (one slider drag,
        one nudge run) replace each other, so they undo as one step. Any
        undo/redo/goto, or an edit with another key, ends the run.

        ``material``: the new material root, when this step changes material
        (a transcript correction). It becomes one revision, undone with the step.
        ``op`` (``{"name", "args"}``) and ``context`` (UI state for undo, WP8)
        are stored with the step.
        """
        self._check_writable()
        if state.rate != self.rate:
            raise HistoryError("error.history.rate_change", rate=state.rate,
                               project_rate=self.rate)
        known = {r[0] for r in self.db.execute("select id from media")}
        for m in state.media:
            if m.id not in known:
                raise HistoryError("error.history.media_not_imported", media_id=m.id)
        current = self.material
        root = {**(current if material is None else material),
                "sync": sync_root(state.sync_groups)}
        changes_material = root != current
        with dbm.tx(self.db):
            head = self._node(self.head)
            if (coalesce is not None and coalesce == self._coalesce
                    and not changes_material and head["material_to"] is None):
                old = head["state"]
                digest = dbm.put_blob(self.db, "edit-state", edit_dict(state))
                self.db.execute(
                    "update nodes set label=?, state=?, op=?, context=?, created_utc=?"
                    " where id=?",
                    (label, digest, json.dumps(op or {}),
                     None if context is None else json.dumps(context),
                     dbm.utc_now(), self.head))
                # A drag passes through many states nobody can return to.
                self.db.execute(
                    "delete from blobs where hash=? and kind='edit-state'"
                    " and not exists (select 1 from nodes where state=?)", (old, old))
            else:
                moved = self._material_rev(root, label) if changes_material else None
                self.head = self._insert(self.edit, self.head, label, state, op=op,
                                         context=context, material=moved)
                self.db.execute("update edits set head=? where id=?",
                                (self.head, self.edit))
        self._coalesce = coalesce
        self._edit_state = replace(state, media=(), sync_groups=())
        self._written()

    def _path(self, target: str) -> tuple[list[dict], list[dict]]:
        """Steps to undo (head first) and redo (top first) to reach ``target``."""
        def chain(node: str | None) -> list[dict]:
            out = []
            while node is not None:
                row = self._node(node)
                out.append(row)
                node = row["parent"]
            return out
        up, down = chain(self.head), chain(target)
        shared = {r["id"] for r in up} & {r["id"] for r in down}
        return ([r for r in up if r["id"] not in shared],
                [r for r in reversed(down) if r["id"] not in shared])

    def _move(self, node: str) -> None:
        self._check_writable()
        try:
            target = self._node(node)
        except KeyError:
            raise HistoryError("error.history.no_step", node=node) from None
        if target["edit"] != self.edit:
            raise HistoryError("error.history.no_step", node=node)
        up, down = self._path(node)
        with dbm.tx(self.db):
            material = self.material_head
            for row in up:
                if row["material_to"] is not None:
                    if material != row["material_to"]:
                        raise HistoryError("error.history.material_changed",
                                           label=row["label"])
                    material = row["material_from"]
            for row in down:
                if row["material_to"] is not None:
                    if material != row["material_from"]:
                        raise HistoryError("error.history.material_changed",
                                           label=row["label"])
                    material = row["material_to"]
            dbm.set_meta(self.db, "material_head", str(material))
            self.db.execute("update edits set head=? where id=?", (node, self.edit))
        self._edit_state = self._load(node)
        self.head, self._coalesce = node, None
        self._written()

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

    def goto(self, node: str) -> None:
        self._move(str(node))

    def nodes(self) -> list[dict]:
        rows = _rows(self.db.execute(
            "select id, parent, label, author, machine, op, created_utc as created,"
            " material_from, material_to from nodes where edit=? order by id",
            (self.edit,)))
        for r in rows:
            r["op"] = json.loads(r["op"])
        return rows

    # -- several edits (WP21 builds on this) -------------------------------

    def create_edit(self, name: str, state: Project | None = None) -> str:
        """A new edit of the same material, starting from ``state`` (default:
        this edit's current state). Returns its id; open it with
        ``History(path, edit=id)``."""
        self._check_writable()
        edit = dbm.uuid7()
        with dbm.tx(self.db):
            self.db.execute("insert into edits(id, name, created_utc) values (?,?,?)",
                            (edit, name, dbm.utc_now()))
            node = self._insert(edit, None, t("history.new_edit", name=name),
                                state or self.state)
            self.db.execute("update edits set head=? where id=?", (node, edit))
        self._written()
        return edit

    def edits(self) -> list[dict]:
        return _rows(self.db.execute(
            "select id, name, created_utc, archived, head from edits"
            " order by created_utc, rowid"))

    # -- checkpoints -------------------------------------------------------

    def checkpoint(self, name: str, kind: str = "manual", copy: str | None = None,
                   node: str | None = None) -> None:
        """Name a step ("v1 sent to Ville"). ``kind``: manual | sent | received."""
        self._check_writable()
        with dbm.tx(self.db):
            self.db.execute(
                "insert or replace into checkpoints(node, name, kind, copy, created_utc)"
                " values (?,?,?,?,?)",
                (node or self.head, name, kind, copy, dbm.utc_now()))
        self._written()

    def checkpoints(self) -> list[dict]:
        return _rows(self.db.execute(
            "select c.node, c.name, c.kind, c.copy, c.created_utc from checkpoints c"
            " join nodes n on n.id = c.node where n.edit=? order by c.created_utc",
            (self.edit,)))

    # -- transcripts -------------------------------------------------------

    def add_transcript(self, media_id: str, words: list[dict],
                       engine: dict | None = None, label: str | None = None) -> int:
        """Store a transcript revision and make it the one ``media_id`` uses.

        Words are in flicks from the media's start (``transcribe``). Using
        them is a material step in this edit, so it undoes, and every edit
        sees it.
        """
        self._check_writable()
        with dbm.tx(self.db):
            digest = dbm.put_blob(self.db, "words", list(words))
            cur = self.db.execute(
                "insert into transcript_revs(media, parent, words, engine, created_utc)"
                " values (?,?,?,?,?)",
                (media_id, self.transcript_rev(media_id), digest,
                 json.dumps(engine or {}), dbm.utc_now()))
            rev = int(cur.lastrowid)
            root = self.material
            root["transcripts"] = {**root["transcripts"], media_id: rev}
            self.commit(label or t("history.transcript", media_id=media_id),
                        self.state, material=root)
        return rev

    def transcript(self, rev: int) -> list[dict]:
        row = self.db.execute("select words from transcript_revs where id=?",
                              (int(rev),)).fetchone()
        if row is None:
            raise KeyError(rev)
        return dbm.get_blob(self.db, row[0])

    def transcript_rev(self, media_id: str) -> int | None:
        rev = self.material["transcripts"].get(media_id)
        return None if rev is None else int(rev)

    def transcripts(self) -> dict[str, list[dict]]:
        """The words every media uses now, for ``transcript.timeline_words``."""
        return {m: self.transcript(r) for m, r in self.material["transcripts"].items()}

    def close(self) -> None:
        self.db.close()
