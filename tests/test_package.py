"""The project package (docs/FORMAT.md): folder, manifest, lock, backups, migration."""

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import caches, cli, messages, migrations, ops, package
from kuulas.clock import frames_to_flicks
from kuulas.history import HistoryError
from kuulas.model import Project

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "v0-project"


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def wav(path: Path, frames: int = 4800, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(frames) * 0.1).astype(np.float32), 48000,
             subtype="PCM_16")
    return path


def lock_files(folder: Path) -> list[Path]:
    """The per-instance lock files in ``locks/`` (none when closed)."""
    return sorted((folder / "locks").glob("*.json"))


def manifest(folder: Path) -> dict:
    return json.loads((folder / "manifest.json").read_text())


def test_new_package_has_manifest_lock_db_media_caches(tmp_path):
    pkg = package.create(tmp_path / "Interview.kuulas")
    root = pkg.path
    for name in ("manifest.json", "project.sqlite"):
        assert (root / name).is_file(), name
    # One lock file per open instance; the shared lock.json is no longer written.
    assert not (root / "lock.json").exists()
    for name in ("media", "media/excerpts", "media/originals", "caches/peaks",
                 "caches/onsets", "caches/analysis", "caches/render", "backups",
                 "recordings"):
        assert (root / name).is_dir(), name
    m = manifest(root)
    assert m["format"] == "kuulas-project"
    assert (m["version"], m["min_reader"]) == (4, 1)
    assert m["written_by"].startswith("kuulas ")
    assert len(m["id"]) == 32
    assert len(m["copy"]) == 32
    assert m["lineage"] == []
    assert m["created_utc"].endswith("Z")
    (mine,) = lock_files(root)
    lock = json.loads(mine.read_text())
    assert lock["host"] == socket.gethostname()
    assert lock["pid"] == os.getpid()
    # The file name carries the host as the lock writer cleans it (characters, 40 long).
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", socket.gethostname())
    host = cleaned[:40].strip("._-") or "host"
    assert mine.name.startswith(f"{host}-")
    assert not pkg.read_only
    # The database knows which project it belongs to, even on its own.
    db = sqlite3.connect(root / "project.sqlite")
    meta = dict(db.execute("select key, value from meta"))
    assert meta["project_id"] == m["id"]
    assert meta["schema_version"] == "4"
    db.close()
    pkg.close()
    assert lock_files(root) == []


def test_create_refuses_an_existing_project(tmp_path):
    package.create(tmp_path / "A.kuulas").close()
    with pytest.raises(package.PackageError):
        package.create(tmp_path / "A.kuulas")


def test_manifest_is_written_atomically(tmp_path, monkeypatch):
    pkg = package.create(tmp_path / "A.kuulas")
    before = (pkg.path / "manifest.json").read_bytes()

    def crash(*_args):
        raise OSError("power cut")

    # The crash lands between writing the temp file and renaming it.
    monkeypatch.setattr(package.os, "replace", crash)
    with pytest.raises(OSError, match="power cut"):
        package.write_manifest(pkg.path, {**manifest(pkg.path), "version": 4})
    assert (pkg.path / "manifest.json").read_bytes() == before
    monkeypatch.undo()
    pkg.close()
    assert package.open_package(pkg.path).manifest["version"] == 4


def test_newer_min_reader_refuses_with_version(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    m = manifest(pkg.path)
    package.write_manifest(pkg.path, {**m, "version": 5, "min_reader": 5,
                                      "written_by": "kuulas 27.01.01.1"})
    with pytest.raises(package.PackageError) as err:
        package.open_package(pkg.path)
    assert err.value.key == "error.package.too_new"
    assert "kuulas 27.01.01.1" in str(err.value)
    # Refusing touched nothing, not even the lock.
    assert lock_files(pkg.path) == []


def test_newer_version_opens_and_keeps_unknown_keys(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    media = pkg.store.import_file(wav(tmp_path / "a.wav"))
    p = ops.add_track(pkg.history.state, track_id="t", name="A")
    p = ops.add_clip(p, "t", media.id, clip_id="c")
    # A newer kuulas wrote keys this one does not know, at every level.
    d = p.to_dict()
    d["future_setting"] = {"x": 1}
    d["tracks"][0]["lane_colour"] = "teal"
    d["tracks"][0]["clips"][0]["take_lane"] = 2
    pkg.history.commit("from the future", Project.from_dict(d))
    pkg.close()
    db = sqlite3.connect(pkg.path / "project.sqlite")
    db.execute("alter table media add column loudness_lufs real")
    db.execute("update media set loudness_lufs=-19.5, extra=? where id=?",
               (json.dumps({"colour": "red"}), media.id))
    db.execute("create table future_things(id integer primary key, what text)")
    db.execute("insert into future_things(what) values ('keep me')")
    db.commit()
    db.close()
    package.write_manifest(pkg.path, {**manifest(pkg.path), "version": 4,
                                      "new_manifest_key": True})

    pkg = package.open_package(pkg.path)
    assert not pkg.read_only
    state = pkg.history.state
    assert state.extra == {"future_setting": {"x": 1}}
    assert state.media_item(media.id).extra == {"colour": "red"}
    # An edit by this version, then a save.
    pkg.history.commit("louder", ops.set_master(state, -2.0))
    # Touching the source makes the store rewrite the row's mtime.
    st = (tmp_path / "a.wav").stat()
    os.utime(tmp_path / "a.wav", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert pkg.store.missing() == []
    pkg.close()

    pkg = package.open_package(pkg.path)
    d = pkg.history.state.to_dict()
    assert d["future_setting"] == {"x": 1}
    assert d["tracks"][0]["lane_colour"] == "teal"
    assert d["tracks"][0]["clips"][0]["take_lane"] == 2
    assert d["master_gain_db"] == -2.0
    pkg.close()
    db = sqlite3.connect(pkg.path / "project.sqlite")
    assert db.execute("select loudness_lufs, extra from media").fetchone() == (
        -19.5, json.dumps({"colour": "red"}))
    assert db.execute("select what from future_things").fetchall() == [("keep me",)]
    db.close()
    m = manifest(pkg.path)
    assert m["version"] == 4
    assert m["new_manifest_key"] is True


def write_lock(folder: Path, host: str, age_s: float) -> dict:
    beat = (datetime.now(UTC) - timedelta(seconds=age_s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lock = {"host": host, "pid": 4242, "user": "ville", "opened_utc": beat,
            "heartbeat_utc": beat}
    (folder / "lock.json").write_text(json.dumps(lock))
    return lock


def test_live_lock_from_another_host_opens_read_only(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    lock = write_lock(pkg.path, "windows-pc", age_s=20)
    pkg = package.open_package(pkg.path)
    assert pkg.read_only
    assert pkg.locked_by["host"] == "windows-pc"
    with pytest.raises(HistoryError) as err:
        pkg.history.commit("edit", ops.set_master(pkg.history.state, -1.0))
    assert "windows-pc" in str(err.value)
    pkg.tick()
    pkg.close()
    # The other host's lock is left exactly as it was.
    assert json.loads((pkg.path / "lock.json").read_text()) == lock


def _lock_from_this_host(folder: Path, pid: int, age_s: float = 5) -> None:
    lock = write_lock(folder, socket.gethostname(), age_s=age_s)
    lock["pid"] = pid
    (folder / "lock.json").write_text(json.dumps(lock))


def _dead_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_fresh_lock_of_a_dead_process_here_is_taken_over_at_once(tmp_path, caplog):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    _lock_from_this_host(pkg.path, _dead_pid(), age_s=5)
    with caplog.at_level("WARNING", logger="kuulas.package"):
        pkg = package.open_package(pkg.path)
    assert not pkg.read_only
    pkg.close()


def test_lock_of_a_live_process_on_this_machine_still_opens_read_only(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    _lock_from_this_host(pkg.path, os.getppid(), age_s=5)
    pkg = package.open_package(pkg.path)
    assert pkg.read_only
    pkg.close()


def test_a_second_open_in_the_same_process_is_read_only(tmp_path):
    # The desktop app keeps every window in one process: a second window on a project that
    # is already open must not get a second writer (its history would fork).
    first = package.create(tmp_path / "A.kuulas")
    second = package.open_package(first.path)
    assert not first.read_only
    assert second.read_only
    assert second.locked_by["pid"] == os.getpid()
    second.close()
    first.close()


def test_closing_the_read_only_second_open_keeps_the_first_ones_lock(tmp_path):
    first = package.create(tmp_path / "A.kuulas")
    second = package.open_package(first.path)
    second.close()
    assert len(lock_files(first.path)) == 1
    third = package.open_package(first.path)
    assert third.read_only
    third.close()
    first.close()
    fourth = package.open_package(first.path)
    assert not fourth.read_only
    fourth.close()


def test_stale_lock_is_taken_over(tmp_path, caplog):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    write_lock(pkg.path, "windows-pc", age_s=10 * 60)
    with caplog.at_level("WARNING", logger="kuulas.package"):
        pkg = package.open_package(pkg.path)
    assert not pkg.read_only
    assert "windows-pc" in caplog.text
    (mine,) = lock_files(pkg.path)
    lock = json.loads(mine.read_text())
    assert (lock["host"], lock["pid"]) == (socket.gethostname(), os.getpid())
    pkg.close()


def write_host_lock(folder: Path, host: str, age_s: float, *, pid: int = 4242,
                    name: str | None = None, now: datetime | None = None) -> Path:
    """What another machine's kuulas leaves in ``locks/`` once Dropbox has synced it."""
    beat = ((now or datetime.now(UTC)) - timedelta(seconds=age_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    path = folder / "locks" / (name or f"{host}-{'ab' * 16}.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"host": host, "pid": pid, "user": "ville",
                                "opened_utc": beat, "heartbeat_utc": beat}))
    return path


def as_host(monkeypatch, host: str) -> None:
    monkeypatch.setattr(package, "_hostname", lambda: host)


def test_two_hosts_the_second_is_refused_while_the_first_heartbeat_is_fresh(
        tmp_path, monkeypatch):
    as_host(monkeypatch, "mac-studio")
    a = package.create(tmp_path / "A.kuulas")
    t0 = datetime.now(UTC)
    a.heartbeat(t0)
    as_host(monkeypatch, "macbook")
    b = package.open_package(a.path, now=t0 + timedelta(seconds=200))
    assert b.read_only
    assert b.locked_by["host"] == "mac-studio"
    with pytest.raises(HistoryError) as err:
        b.history.commit("edit", ops.set_master(b.history.state, -1.0))
    assert "mac-studio" in str(err.value)
    b.close()
    # The reader wrote no lock of its own and left the holder's alone.
    assert [p.name.rsplit("-", 1)[0] for p in lock_files(a.path)] == ["mac-studio"]
    a.close()


def test_two_hosts_the_second_may_open_once_the_first_heartbeat_is_old(
        tmp_path, monkeypatch, caplog):
    as_host(monkeypatch, "mac-studio")
    a = package.create(tmp_path / "A.kuulas")
    t0 = datetime.now(UTC)
    a.heartbeat(t0)
    as_host(monkeypatch, "macbook")
    # Just under the limit: still held (a slow sync must not look like a crash).
    assert package.open_package(
        a.path, now=t0 + timedelta(seconds=package.STALE_FOREIGN_S - 5)).read_only
    with caplog.at_level("WARNING", logger="kuulas.package"):
        b = package.open_package(
            a.path, now=t0 + timedelta(seconds=package.STALE_FOREIGN_S + 5))
    assert not b.read_only
    assert "mac-studio" in caplog.text
    hosts = sorted(p.name.rsplit("-", 1)[0] for p in lock_files(a.path))
    assert hosts == ["mac-studio", "macbook"]
    b.close()


def test_heartbeat_is_every_minute_and_foreign_staleness_allows_for_sync_delay():
    assert package.HEARTBEAT_S == 60
    assert package.STALE_FOREIGN_S == 300
    assert package.STALE_FOREIGN_S >= 4 * package.HEARTBEAT_S


def test_a_dead_pid_on_this_host_is_taken_over_from_locks_too(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    write_host_lock(pkg.path, socket.gethostname(), 5, pid=_dead_pid())
    pkg = package.open_package(pkg.path)
    assert not pkg.read_only
    pkg.close()


def test_a_live_pid_on_this_host_in_locks_blocks(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    write_host_lock(pkg.path, socket.gethostname(), 5, pid=os.getppid())
    pkg = package.open_package(pkg.path)
    assert pkg.read_only
    pkg.close()


def test_conflicted_copies_are_ignored_and_never_crash_the_open(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    # A fresh foreign lock, but in a file Dropbox renamed: not a lock.
    write_host_lock(pkg.path, "windows-pc", 5,
                    name="windows-pc-abab (Olli's conflicted copy 2026-10-18).json")
    (pkg.path / "locks" / "garbage conflicted copy.json").write_text("{not json")
    (pkg.path / "lock conflicted copy.json").write_text("{not json")
    (pkg.path / "lock (Olli's MacBook's conflicted copy 2026-10-18).json").write_text(
        json.dumps({"host": "x", "pid": 1, "heartbeat_utc": "2999-01-01T00:00:00Z"}))
    pkg = package.open_package(pkg.path)
    assert not pkg.read_only
    pkg.close()


def test_unreadable_lock_files_are_nobodys(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    (pkg.path / "locks" / "half-written.json").write_text('{"host": ')
    pkg = package.open_package(pkg.path)
    assert not pkg.read_only
    pkg.close()


def test_heartbeats_write_only_the_own_file(tmp_path, monkeypatch):
    as_host(monkeypatch, "mac-studio")
    a = package.create(tmp_path / "A.kuulas")
    other = write_host_lock(a.path, "macbook", 1000)  # stale, young enough to keep
    before = other.read_text()
    write_lock(a.path, "windows-pc", age_s=1000)
    legacy_before = (a.path / "lock.json").read_text()
    (mine,) = [p for p in lock_files(a.path) if p.name.startswith("mac-studio")]
    for i in range(1, 4):
        a.tick(now=datetime.now(UTC) + timedelta(seconds=60 * i))
    assert other.read_text() == before
    assert (a.path / "lock.json").read_text() == legacy_before
    assert json.loads(mine.read_text())["host"] == "mac-studio"
    assert sorted(p.name for p in (a.path / "locks").iterdir()) == sorted(
        [mine.name, other.name])
    a.close()


def test_close_removes_only_the_own_file(tmp_path, monkeypatch):
    as_host(monkeypatch, "mac-studio")
    a = package.create(tmp_path / "A.kuulas")
    other = write_host_lock(a.path, "macbook", 1000)
    a.close()
    assert lock_files(a.path) == [other]


def test_old_foreign_locks_are_swept_after_an_hour_young_ones_kept(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    old = write_host_lock(pkg.path, "old-pc", 2 * 3600)
    young = write_host_lock(pkg.path, "young-pc", 20 * 60, name="young-pc-1.json")
    pkg = package.open_package(pkg.path)
    assert not old.exists()
    assert young.exists()
    pkg.close()


def test_legacy_lock_json_from_another_host_still_blocks_and_is_never_written(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    legacy = write_lock(pkg.path, "windows-pc", age_s=20)
    b = package.open_package(pkg.path)
    assert b.read_only
    b.tick(now=datetime.now(UTC) + timedelta(seconds=600))
    b.close()
    assert json.loads((pkg.path / "lock.json").read_text()) == legacy
    # A stale legacy lock does not block, and an opener does not write one.
    write_lock(pkg.path, "windows-pc", age_s=1000)
    c = package.open_package(pkg.path)
    assert not c.read_only
    c.tick(now=datetime.now(UTC) + timedelta(seconds=600))
    c.close()


def test_a_failed_open_removes_its_own_lock_file(tmp_path, monkeypatch):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    package.write_manifest(pkg.path, {**manifest(pkg.path), "version": 1})

    def boom(*a, **k):
        raise RuntimeError("upgrade failed")
    monkeypatch.setattr(package, "_upgrade", boom)
    with pytest.raises(RuntimeError):
        package.open_package(pkg.path)
    assert lock_files(pkg.path) == []


def test_heartbeat_refreshes_the_lock(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    later = datetime.now(UTC) + timedelta(minutes=5)
    pkg.tick(now=later)
    (mine,) = lock_files(pkg.path)
    lock = json.loads(mine.read_text())
    assert lock["heartbeat_utc"] == later.strftime("%Y-%m-%dT%H:%M:%SZ")
    pkg.close()


def backup_name(t: datetime) -> str:
    return f"auto-{t.strftime('%Y%m%dT%H%M%SZ')}.sqlite"


def test_backup_retention_keeps_12_recent_and_one_per_day(tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    times = [now - timedelta(minutes=10 * i) for i in range(20)]           # today
    times += [now - timedelta(days=d, hours=h) for d in range(1, 20) for h in (1, 5)]
    for t in times:
        (folder / backup_name(t)).write_bytes(b"x")
    (folder / "pre-migration-v0-20260101T000000Z.sqlite").write_bytes(b"x")
    package.prune_backups(folder, now=now, tz=UTC)
    kept = {p.name for p in folder.iterdir()}
    newest = sorted(times, reverse=True)
    want = {backup_name(t) for t in newest[:12]}
    # The last one of each day for 14 days (today included).
    for d in range(14):
        day = (now - timedelta(days=d)).date()
        want.add(backup_name(max(t for t in times if t.date() == day)))
    assert kept == want | {"pre-migration-v0-20260101T000000Z.sqlite"}


def test_backup_never_writes_the_live_file(tmp_path, monkeypatch):
    pkg = package.create(tmp_path / "A.kuulas")
    # The quiet-tick WAL checkpoint legitimately rewrites the live file (tested
    # below); this test is about the backup alone.
    monkeypatch.setattr(pkg, "checkpoint", lambda: None)
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -1.0))
    live = [pkg.path / n for n in ("project.sqlite", "project.sqlite-wal")]

    def snapshot():
        return [(p.read_bytes(), p.stat().st_mtime_ns) if p.exists() else None
                for p in live]

    before = snapshot()
    start = datetime.now(UTC)
    # Nothing new since the last backup: no backup.
    made = pkg.tick(now=start + timedelta(minutes=11))
    assert made is not None
    assert pkg.tick(now=start + timedelta(minutes=30)) is None
    assert snapshot() == before
    pkg.wait_compressed()
    assert snapshot() == before
    # Stored xz-compressed since v26.10.20 (test_backup_size.py).
    backups = list((pkg.path / "backups").glob("auto-*.sqlite.xz"))
    assert len(backups) == 1
    assert not list((pkg.path / "backups").glob("*.partial"))
    plain = package.read_backup(backups[0], tmp_path / "plain.sqlite")
    copy = sqlite3.connect(plain)
    assert copy.execute("select count(*) from nodes").fetchone()[0] == 2
    copy.close()
    pkg.close()


def old_states() -> list[tuple[int, int | None, str, dict]]:
    db = sqlite3.connect(FIXTURE / "project.sqlite")
    rows = db.execute("select id, parent, label, state from nodes order by id").fetchall()
    db.close()
    return [(i, par, lab, json.loads(zlib.decompress(s))) for i, par, lab, s in rows]


def old_transcripts() -> dict[int, list[dict]]:
    db = sqlite3.connect(FIXTURE / "project.sqlite")
    rows = db.execute("select id, words from transcripts").fetchall()
    db.close()
    return {i: json.loads(zlib.decompress(w)) for i, w in rows}


def without_sync(tracks: list[dict]) -> list[dict]:
    gone = ("sync", "sync_origin")
    return [{"speaker": "", **t, "clips": [{k: v for k, v in c.items() if k not in gone}
                            for c in t["clips"]]} for t in tracks]


def test_migration_v0_to_v1_keeps_every_state_media_and_transcript(tmp_path):
    folder = tmp_path / "Old.kuulas"
    shutil.copytree(FIXTURE, folder)
    olds = old_states()
    pkg = package.open_package(folder)
    assert manifest(folder)["version"] == 4
    assert len(list((folder / "backups").glob("pre-migration-v0-*.sqlite"))) == 1
    h = pkg.history

    # Every state, same tree shape and labels, same edit content.
    nodes = h.nodes()
    assert [n["label"] for n in nodes] == [lab for _, _, lab, _ in olds]
    new_id = {old[0]: n["id"] for old, n in zip(olds, nodes, strict=True)}
    # The fixture's head is its newest node.
    assert h.head == new_id[max(o[0] for o in olds)]
    for (old_id, parent, _, state), node in zip(olds, nodes, strict=True):
        assert node["parent"] == (new_id[parent] if parent else None)
        h.goto(new_id[old_id])
        got = h.state.to_dict()
        assert got["rate"] == state["rate"]
        assert got["master_gain_db"] == state["master_gain_db"]
        assert got["buses"] == state["buses"]
        # Clips lose their sync fields: membership is per media now (WP30).
        assert json.loads(json.dumps(got["tracks"])) == without_sync(state["tracks"])
        assert "transcripts" not in got
    head_old = max(olds, key=lambda o: o[0])  # the fixture ends on its newest node
    h.goto(new_id[head_old[0]])

    # Media: rows instead of JSON files, with the names the states used.
    by_id = {m.id: m for m in h.state.media}
    for media in head_old[3]["media"]:
        assert by_id[media["id"]].name == media["name"]
        assert by_id[media["id"]].frames == media["frames"]
        assert by_id[media["id"]].sha256 == media["sha256"]
    assert not list((folder / "media").glob("*.json"))
    assert not list((folder / "media").glob("*.peaks.npy"))
    assert len(list((folder / "caches" / "peaks").glob("*.npy"))) == 2
    linked = [m for m in by_id if pkg.store.is_linked(m)]
    assert len(linked) == 1
    assert pkg.store.missing() == linked  # its source was deleted after the fixture
    seen = json.loads(Path(FIXTURE / "media" / "seen.json").read_text())
    for digest, paths in seen.items():
        assert set(pkg.store.seen_paths(digest)) == set(paths)
    working = next(m for m in by_id if m not in linked)
    assert pkg.store.read(working, 0, 4800).any()

    # Sync: the head state's clip fields became per-media members, in flicks.
    [group] = h.state.sync_groups
    anna, ville = (m["id"] for m in head_old[3]["media"])
    assert (group.id, group.main) == ("g1", anna)
    assert dict(group.members) == {anna: 0, ville: frames_to_flicks(120, 48000)}

    # Transcripts: every revision, on the recording clock, and the head
    # state's choice is current.
    for rev, words in old_transcripts().items():
        assert h.transcript(rev) == [
            {**w, "s": frames_to_flicks(w["s"], 48000),
             "e": frames_to_flicks(w["e"], 48000)} for w in words]
    pointers = dict(head_old[3]["transcripts"])
    for media_id, rev in pointers.items():
        assert h.transcript_rev(media_id) == rev
    pkg.close()

    # Opening again does not migrate again.
    pkg = package.open_package(folder)
    # (three: v0 to v1, v1 to v2 and v2 to v3 each take their own backup)
    assert len(list((folder / "backups").glob("pre-migration-*.sqlite"))) == 4
    pkg.close()


def test_caches_can_be_deleted_and_are_rebuilt(tmp_path, caplog):
    pkg = package.create(tmp_path / "A.kuulas")
    media = pkg.store.import_file(wav(tmp_path / "a.wav", frames=48000))
    first = pkg.store.peaks(media.id)
    pkg.close()
    shutil.rmtree(pkg.path / "caches")
    pkg = package.open_package(pkg.path)
    with caplog.at_level("INFO", logger="kuulas.media"):
        again = pkg.store.peaks(media.id)
    np.testing.assert_array_equal(again, first)
    assert media.id in caplog.text
    assert len(list((pkg.path / "caches" / "peaks").glob("*.npy"))) == 1
    pkg.close()


def test_cache_key_follows_inputs_params_and_algorithm():
    a = caches.key(["abc"], {"per": 256}, "peaks@1")
    assert a == caches.key(["abc"], {"per": 256}, "peaks@1")
    assert a != caches.key(["abd"], {"per": 256}, "peaks@1")
    assert a != caches.key(["abc"], {"per": 512}, "peaks@1")
    assert a != caches.key(["abc"], {"per": 256}, "peaks@2")


def test_info_reports_manifest_sizes_media_and_backups(tmp_path, capsys):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.store.import_file(wav(tmp_path / "a.wav"))            # linked
    pkg.store.import_file(wav(tmp_path / "b.wav", seed=1), copy=True)  # working
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -1.0))
    pkg.backup()
    pkg.close()
    (tmp_path / "a.wav").unlink()
    info = package.info(pkg.path)
    assert info["manifest"]["format"] == "kuulas-project"
    assert info["media"] == {"linked": 0, "working": 1, "excerpt": 0, "missing": 1}
    assert info["backups"] == 1
    assert info["sizes"]["project.sqlite"] > 0
    assert cli.main(["info", str(pkg.path)]) == 0
    out = capsys.readouterr().out
    assert "kuulas-project" in out
    assert "missing" in out
    # info only reads: no lock was taken.
    assert lock_files(pkg.path) == []


def test_migrated_sync_keeps_the_main_pieces_origin_when_clips_disagree(caplog):
    # Two pieces of Ville's file with different origins (impossible with v0's
    # own edits, but a hand-edited or buggy file could have it): keep the
    # piece that plays against the main clip, and say so.
    def clip(cid, media, start, origin, sync="g"):
        return {"id": cid, "media": media, "start": start, "offset": 0, "length": 100,
                "sync": sync, "sync_origin": origin}
    state = {"sync_groups": [["g", "ma"]], "tracks": [
        {"id": "A", "clips": [clip("ca", "ma", 0, 0)]},
        {"id": "V", "clips": [clip("v1", "mv", 50, 30), clip("v2", "mv", 500, 70),
                              clip("loose", "mx", 0, 0, sync=None)]}]}
    with caplog.at_level("WARNING", logger="kuulas.package"):
        groups = migrations.sync_from_v0(state, rate=1000)
    assert groups == {"g": {"main": "ma", "members": {
        "ma": 0, "mv": frames_to_flicks(30, 1000)}}}
    assert "mv" in caplog.text


def test_create_refuses_a_rate_flicks_cannot_hold(tmp_path):
    with pytest.raises(package.PackageError) as err:
        package.create(tmp_path / "Odd.kuulas", rate=37800)
    assert err.value.key == "error.clock.rate"
    assert not (tmp_path / "Odd.kuulas").exists()


# -- WAL hygiene ------------------------------------------------------------------


def wal_size(folder: Path) -> int:
    wal = folder / "project.sqlite-wal"
    return wal.stat().st_size if wal.exists() else 0


def test_a_quiet_tick_after_a_write_burst_truncates_the_wal(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -2.0))
    assert wal_size(pkg.path) > 0
    t0 = datetime.now(UTC)
    pkg.tick(now=t0 + timedelta(seconds=60))   # may still be bursting
    pkg.tick(now=t0 + timedelta(seconds=120))  # nothing new since the last tick
    assert wal_size(pkg.path) == 0
    pkg.close()


def test_close_leaves_a_complete_main_file_and_no_wal_content(tmp_path):
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -2.0))
    pkg.close()
    assert wal_size(pkg.path) == 0
    # The main file alone holds the edit: copy only it, as a half-synced folder would.
    alone = tmp_path / "alone.sqlite"
    shutil.copy(pkg.path / "project.sqlite", alone)
    db = sqlite3.connect(alone)
    assert db.execute("select count(*) from meta").fetchone()[0] > 0
    assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
    db.close()
    assert not (tmp_path / "alone.sqlite-wal").exists()
