"""Format upgrades: forward-only, each after a backup (docs/FORMAT.md).

``upgrade`` brings a package to ``package.VERSION``. Before any migration
runs, ``project.sqlite`` is copied to
``backups/pre-migration-vN-<UTC>.sqlite`` with SQLite's online backup API.
Each migration runs in one transaction; the manifest is written after it,
and its presence is what marks the new format.

v0 is the layout before the format had a version: ``project.sqlite`` with
integer node ids and transcripts in their own table, and per-media JSON
files, ``seen.json`` and peaks beside the audio in ``media/``. Those
projects exist only on developer machines, so this is tested against a
fixture (``tests/fixtures/v0-project``), not rolled out.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import zlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from . import caches
from . import db as dbm
from .clock import frames_to_flicks
from .history import EMPTY_MATERIAL, MAIN_EDIT, edit_dict
from .media import PEAK_FRAMES, PEAKS_ALGORITHM
from .messages import t
from .model import Project

log = logging.getLogger("kuulas.package")

#: Keys of a v0 ``media/<id>.json`` that have a column; any other key goes
#: into the row's ``extra``, so nothing is lost.
_V0_MEDIA_KEYS = {"channels", "frames", "subtype", "lossless", "linked", "path",
                  "size", "mtime_ns", "sha256"}


def _utc(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_before(db: sqlite3.Connection, folder: Path, version: int) -> Path:
    """The pre-migration copy, by the online backup API (never a file copy:
    the WAL may hold committed pages the main file does not have yet)."""
    backups = folder / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backups / f"pre-migration-v{version}-{stamp}.sqlite"
    partial = target.with_name(target.name + ".partial")
    copy = sqlite3.connect(partial)
    try:
        db.backup(copy)
    finally:
        copy.close()
    partial.replace(target)
    return target


def migrate_0_to_1(db: sqlite3.Connection, folder: Path) -> None:
    """Steps 2 to 4 of FORMAT.md's "Migration from today's layout"."""
    old_nodes = db.execute(
        "select id, parent, label, state, created from nodes order by id").fetchall()
    head = int(db.execute("select value from meta where key='head'").fetchone()[0])
    old_words = db.execute(
        "select id, media, words, created from transcripts order by id").fetchall()
    states = {i: json.loads(zlib.decompress(s)) for i, _, _, s, _ in old_nodes}
    rate = int(states[head]["rate"])

    # What the states said about each media (name, time reference); the
    # newest state wins.
    described: dict[str, dict] = {}
    for i, *_ in old_nodes:
        for m in states[i].get("media", ()):
            described[m["id"]] = m
    media_dir = folder / "media"
    files = {p.stem: json.loads(p.read_text()) for p in sorted(media_dir.glob("m*.json"))}
    seen_file = media_dir / "seen.json"
    seen = json.loads(seen_file.read_text()) if seen_file.exists() else {}
    now = dbm.utc_now()
    ids = dbm.Uuid7Clock()

    with dbm.tx(db):
        db.execute("alter table nodes rename to v0_nodes")
        db.execute("alter table meta rename to v0_meta")
        dbm.create_tables(db)
        dbm.set_meta(db, "schema_version", "1")
        dbm.set_meta(db, "project_rate", str(rate))
        dbm.set_meta(db, "created_utc", _utc(old_nodes[0][4]))

        for media_id in sorted(set(files) | set(described)):
            db.execute(*_media_row(media_id, files.get(media_id),
                                   described.get(media_id), rate, now))
        for digest, paths in seen.items():
            for where in paths:
                db.execute("insert or ignore into media_paths values (?,?,?,?)",
                           (digest, where, now, now))

        last_rev: dict[str, int] = {}
        for rev, media_id, blob, created in old_words:
            words = [{**w, "s": frames_to_flicks(w["s"], rate),
                      "e": frames_to_flicks(w["e"], rate)}
                     for w in json.loads(zlib.decompress(blob))]
            db.execute("insert into transcript_revs values (?,?,?,?,?,?)",
                       (rev, media_id, last_rev.get(media_id),
                        dbm.put_blob(db, "words", words), "{}", _utc(created)))
            last_rev[media_id] = rev
        pointers = states[head].get("transcripts", ())
        root = {**EMPTY_MATERIAL, "transcripts": {m: int(r) for m, r in pointers},
                "sync": sync_from_v0(states[head], rate)}
        db.execute("insert into material_revs values (1, null, ?, ?, ?)",
                   (t("history.migrated"), dbm.put_blob(db, "material", root), now))
        dbm.set_meta(db, "material_head", "1")

        new_ids: dict[int, str] = {}
        for i, parent, label, _, created in old_nodes:
            new_ids[i] = ids.next(round(created * 1000))
            state = Project.from_dict(_v0_edit_state(states[i]))
            db.execute(
                "insert into nodes(id, edit, parent, author, machine, label, op, state,"
                " created_utc) values (?,?,?,?,?,?,?,?,?)",
                (new_ids[i], MAIN_EDIT, new_ids.get(parent), "", "", label, "{}",
                 dbm.put_blob(db, "edit-state", edit_dict(state)), _utc(created)))
        db.execute("insert into edits(id, name, created_utc, head) values (?,?,?,?)",
                   (MAIN_EDIT, t("history.main_edit"), _utc(old_nodes[0][4]),
                    new_ids[head]))
        db.execute("drop table v0_nodes")
        db.execute("drop table v0_meta")
        db.execute("drop table transcripts")


def migrate_1_to_2(db: sqlite3.Connection, folder: Path) -> None:  # noqa: ARG001 - the migration signature
    """WP41: every material root gains empty ``people``, ``interviews`` and
    ``media_person``. Rewritten in place in every revision (not as a new
    revision), so the steps' ``material_from``/``material_to`` still point at
    the same moments and undo is unaffected. Unknown keys stay."""
    with dbm.tx(db):
        for rev, root in db.execute("select id, root from material_revs").fetchall():
            data = dbm.get_blob(db, root)
            for key in ("people", "interviews", "media_person", "speakers"):
                data.setdefault(key, {})
            db.execute("update material_revs set root=? where id=?",
                       (dbm.put_blob(db, "material", data), rev))
        db.execute("delete from blobs where kind='material'"
                   " and hash not in (select root from material_revs)")
        dbm.set_meta(db, "schema_version", "2")


def _v0_edit_state(state: dict) -> dict:
    """A v0 state without what became material: media, transcript pointers,
    sync groups, and the clips' sync fields (membership is per media now)."""
    d = {k: v for k, v in state.items() if k not in ("transcripts", "sync_groups")}
    d["media"] = []
    d["tracks"] = [{**tr, "clips": [{k: v for k, v in c.items()
                                     if k not in ("sync", "sync_origin")}
                                    for c in tr.get("clips", ())]}
                   for tr in state.get("tracks", ())]
    return d


def _overlap(clip: dict, others: list[dict]) -> int:
    end = clip["start"] + clip["length"]
    return max((min(end, o["start"] + o["length"]) - max(clip["start"], o["start"])
                for o in others), default=0)


def sync_from_v0(state: dict, rate: int) -> dict:
    """v0's per-clip sync fields as per-media members (FORMAT.md, step 4).

    Every clip of a media carried the same origin in v0 (marking moved the
    whole file). If pieces of one media disagree anyway, the piece that
    plays against the main media's pieces wins, and a warning says so.
    """
    clips = [c for tr in state.get("tracks", ()) for c in tr.get("clips", ())]
    out: dict[str, dict] = {}
    owner: dict[str, str] = {}
    for gid, main in state.get("sync_groups", ()):
        in_group = [c for c in clips if c.get("sync") == gid]
        if not in_group:
            continue  # every clip was marked into a later group
        mains = [c for c in in_group if c["media"] == main]
        pieces: dict[str, list[dict]] = {}
        for c in in_group:
            if c["media"] != main:
                pieces.setdefault(c["media"], []).append(c)
        members = {main: 0}
        for media_id, own in sorted(pieces.items()):
            own.sort(key=lambda c: (-_overlap(c, mains), c["start"], c["id"]))
            origin = int(own[0].get("sync_origin", 0))
            if len({int(c.get("sync_origin", 0)) for c in own}) > 1:
                log.warning(t("log.migrate.sync_disagrees", media_id=media_id, group=gid,
                              clip_id=own[0]["id"]))
            members[media_id] = frames_to_flicks(origin, rate)
        for media_id in members:
            previous = owner.get(media_id)
            if previous is not None and previous in out:
                out[previous]["members"].pop(media_id, None)
            owner[media_id] = gid
        out[gid] = {"main": main, "members": members}
    return out


def _media_row(media_id: str, file: dict | None, state: dict | None, rate: int,
               now: str) -> tuple[str, tuple]:
    state = state or {}
    file = file or {}
    linked = bool(file.get("linked"))
    source = file.get("path") or file.get("source")
    name = state.get("name") or (Path(source).name if source else media_id)
    time_ref = int(state.get("time_ref") or 0)
    extra = {k: v for k, v in file.items() if k not in _V0_MEDIA_KEYS}
    if not file:
        # In a state but never imported through the store: no file to point to.
        extra["v0_no_file"] = True
    digest = file.get("sha256") or state.get("sha256") or f"unknown:{media_id}"
    return ("insert into media(id, sha256, name, storage, channels, source_rate,"
            " source_frames, subtype, lossless, time_ref_flicks, linked_path,"
            " linked_size, linked_mtime_ns, extra, added_utc)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (media_id, digest, name, "linked" if linked else "working",
             int(file.get("channels") or state.get("channels") or 1), rate,
             int(file.get("frames") or state.get("frames") or 0), file.get("subtype"),
             int(bool(file.get("lossless"))),
             frames_to_flicks(time_ref, rate) if time_ref else None,
             file.get("path") if linked else None, file.get("size") if linked else None,
             file.get("mtime_ns") if linked else None, json.dumps(extra), now))


def finish_v1(db: sqlite3.Connection, folder: Path) -> None:
    """The file moves after the v0 transaction (steps 3 and 5). Safe to run
    again: a crash before the manifest is written lands here on next open."""
    media_dir = folder / "media"
    rate = int(dbm.meta(db, "project_rate") or 48000)
    for media_id, digest in db.execute("select id, sha256 from media"):
        old = media_dir / f"{media_id}.peaks.npy"
        if old.exists():
            key = caches.key([digest], {"per": PEAK_FRAMES, "rate": rate},
                             PEAKS_ALGORITHM)
            target = caches.path(folder / "caches", "peaks", key, "npy")
            target.parent.mkdir(parents=True, exist_ok=True)
            old.replace(target)


def cleanup_v0(folder: Path) -> None:
    """Remove what v1 replaced, once the manifest marks the project as v1."""
    media_dir = folder / "media"
    for path in [*media_dir.glob("m*.json"), *media_dir.glob("*.peaks.npy"),
                 media_dir / "seen.json"]:
        path.unlink(missing_ok=True)


#: ``version -> migration to version + 1``.
MIGRATIONS: dict[int, Callable[[sqlite3.Connection, Path], None]] = {
    0: migrate_0_to_1, 1: migrate_1_to_2}


def upgrade(db: sqlite3.Connection, folder: Path, version: int, target: int) -> None:
    """Run every migration from ``version`` up to ``target``, each after a backup."""
    for v in range(version, target):
        log.info(t("log.package.migrating", source=v, target=v + 1))
        backup_before(db, folder, v)
        MIGRATIONS[v](db, folder)
    if version == 0:
        finish_v1(db, folder)
