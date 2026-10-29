"""Incremental backup storage is content addressed, restorable, and fail closed."""

import hashlib
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from kuulas import incremental_backup as incremental
from kuulas import ops, package, priority
from kuulas.history import History


def _database(tmp_path):
    pkg = package.create(tmp_path / "source.kuulas")
    # Enough stable, incompressible pages to detect copying the whole DB again.
    db = pkg.history.db
    db.execute("create table extra(payload blob)")
    db.executemany("insert into extra values (?)", [
        (hashlib.shake_256(str(i).encode()).digest(65536),) for i in range(32)])
    return pkg


def test_only_new_content_is_appended_and_each_snapshot_restores(tmp_path):
    pkg = _database(tmp_path)
    folder = tmp_path / "backups"
    folder.mkdir()
    first = folder / "auto-20261029T010000Z.kbackup"
    second = folder / "auto-20261029T011000Z.kbackup"
    incremental.write(pkg.db_path, first)
    before = incremental.storage_bytes([first])
    pkg.history.commit("gain", ops.set_master(pkg.history.state, -3))
    incremental.write(pkg.db_path, second)
    assert incremental.storage_bytes([first, second]) < before * 1.1
    for src, gain in ((first, 0), (second, -3)):
        restored = package.read_backup(src, tmp_path / "restored.sqlite")
        history = History(restored)
        assert history.state.master_gain_db == gain
        assert history.db.execute("select count(*) from extra").fetchone()[0] == 32
        history.close()
    pkg.close()


@pytest.mark.parametrize("damage", ["missing", "corrupt", "manifest"])
def test_corruption_never_replaces_restore_destination(tmp_path, damage):
    pkg = _database(tmp_path)
    target = tmp_path / "auto-20261029T010000Z.kbackup"
    incremental.write(pkg.db_path, target)
    repository = tmp_path / incremental.REPOSITORY
    if damage == "missing":
        repository.unlink()
    elif damage == "manifest":
        target.write_text('{"format": "wrong"}', encoding="utf-8")
    else:
        db = sqlite3.connect(repository)
        db.execute("update chunks set data=x'1234'")
        db.commit()
        db.close()
    dest = tmp_path / "existing.sqlite"
    dest.write_bytes(b"keep")
    with pytest.raises(package.PackageError):
        package.read_backup(target, dest)
    assert dest.read_bytes() == b"keep"
    assert not list(tmp_path.glob("*.partial"))
    pkg.close()


def test_cancelled_write_publishes_no_manifest_or_temporary_snapshot(tmp_path):
    pkg = _database(tmp_path)
    cancelled = threading.Event()
    cancelled.set()
    target = tmp_path / "auto-20261029T010000Z.kbackup"
    with pytest.raises(priority.CancelledError):
        incremental.write(pkg.db_path, target, cancelled)
    assert not target.exists()
    assert not list(tmp_path.glob("*.partial"))
    pkg.close()


def test_collect_keeps_shared_chunks_and_refuses_an_unreadable_manifest(tmp_path):
    pkg = _database(tmp_path)
    first = tmp_path / "auto-20261029T010000Z.kbackup"
    second = tmp_path / "auto-20261029T011000Z.kbackup"
    incremental.write(pkg.db_path, first)
    pkg.history.commit("gain", ops.set_master(pkg.history.state, -3))
    incremental.write(pkg.db_path, second)
    first.unlink()
    incremental.collect(tmp_path)
    restored = package.read_backup(second, tmp_path / "restored.sqlite")
    assert restored.is_file()
    before = incremental.storage_bytes([second])
    (tmp_path / "auto-20261029T012000Z.kbackup").write_text("broken", encoding="utf-8")
    assert incremental.collect(tmp_path) is False
    assert incremental.storage_bytes([second]) == before
    pkg.close()


def test_snapshot_remains_consistent_when_source_is_written_during_copy(tmp_path,
                                                                       monkeypatch):
    pkg = _database(tmp_path)
    entered = threading.Event()
    wrote = threading.Event()
    real = priority.checkpoint
    failures = []
    checkpoints = 0

    def checkpoint(cancel=None, **kw):
        nonlocal checkpoints
        checkpoints += 1
        if checkpoints == 2:
            entered.set()
            assert wrote.wait(5)
        real(cancel, **kw)

    def writer():
        assert entered.wait(5)
        try:
            pkg.history.commit("gain", ops.set_master(pkg.history.state, -7))
        except (OSError, sqlite3.Error, RuntimeError) as error:
            failures.append(error)
        finally:
            wrote.set()

    monkeypatch.setattr(priority, "checkpoint", checkpoint)
    worker = threading.Thread(target=writer)
    worker.start()
    target = tmp_path / "auto-20261029T010000Z.kbackup"
    incremental.write(pkg.db_path, target, threading.Event())
    worker.join(5)
    assert not failures
    restored = package.read_backup(target, tmp_path / "restored.sqlite")
    history = History(restored)
    assert history.state.master_gain_db == -7
    history.close()
    pkg.close()


def test_periodic_backups_share_content_after_the_first_standalone_copy(tmp_path):
    pkg = _database(tmp_path)
    now = datetime.now(UTC)
    pkg.history.commit("first", ops.set_master(pkg.history.state, -1))
    baseline = pkg.tick(now + timedelta(minutes=11))
    assert baseline is not None
    assert baseline.suffix == ".sqlite"
    pkg.history.commit("second", ops.set_master(pkg.history.state, -2))
    second = pkg.tick(now + timedelta(minutes=22))
    assert second.suffix == incremental.SUFFIX
    restored = package.read_backup(second, tmp_path / "check.sqlite")
    history = History(restored)
    assert history.state.master_gain_db == -2
    history.close()
    pkg.close()
    latest = package.auto_backups(pkg.path / "backups")[0][1]
    assert all(p.suffix != incremental.SUFFIX for p in latest)


def test_timer_defers_all_heavy_work_during_playback_or_recent_input(tmp_path,
                                                                  monkeypatch):
    pkg = _database(tmp_path)
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -1))
    monkeypatch.setattr(priority.GATE, "interactive", lambda: True)
    monkeypatch.setattr(pkg, "checkpoint", lambda: pytest.fail("busy checkpoint"))
    assert pkg.tick(datetime.now(UTC) + timedelta(minutes=11)) is None
    assert package.auto_backups(pkg.path / "backups") == []
    monkeypatch.undo()
    pkg.close()


def test_close_writes_a_standalone_final_snapshot_and_backup_failure_is_soft(tmp_path,
                                                                           monkeypatch):
    pkg = _database(tmp_path)
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -8))
    pkg.close()
    (_, paths), = package.auto_backups(pkg.path / "backups")
    restored = package.read_backup(paths[0], tmp_path / "check.sqlite")
    history = History(restored)
    assert history.state.master_gain_db == -8
    history.close()
    again = package.open_package(pkg.path)
    again.history.commit("edit", ops.set_master(again.history.state, -9))

    def full(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(again, "backup", full)
    again.close()
    history = History(pkg.db_path)
    assert history.state.master_gain_db == -9
    history.close()


def test_retention_counts_shared_chunks_once_and_keeps_newest_snapshots(tmp_path):
    pkg = _database(tmp_path)
    folder = pkg.path / "backups"
    now = datetime.now(UTC)
    refs = []
    for minute in range(15):
        stamp = (now - timedelta(minutes=30 - minute)).strftime("%Y%m%dT%H%M%SZ")
        refs.append(incremental.write(pkg.db_path, folder / f"auto-{stamp}.kbackup"))
    size = incremental.storage_bytes(refs)
    removed = package.prune_backups(folder, now=now, budget=size)
    assert len(removed) == 3
    assert len(package.auto_backups(folder)) == package.KEEP_RECENT
    for ref in refs[3:]:
        package.read_backup(ref, tmp_path / "restored.sqlite")
    pkg.close()


def test_failure_to_publish_keeps_existing_restorable_snapshot(tmp_path, monkeypatch):
    pkg = _database(tmp_path)
    first = tmp_path / "auto-20261029T010000Z.kbackup"
    second = tmp_path / "auto-20261029T011000Z.kbackup"
    incremental.write(pkg.db_path, first)
    original = first.read_bytes()
    real = incremental.os.fsync
    calls = 0

    def disk_full(fd):
        nonlocal calls
        calls += 1
        if calls == 3:  # staging snapshot durable; manifest flush fails
            raise OSError("disk full")
        return real(fd)

    monkeypatch.setattr(incremental.os, "fsync", disk_full)
    with pytest.raises(OSError, match="disk full"):
        incremental.write(pkg.db_path, second)
    monkeypatch.undo()
    assert not second.exists()
    assert not list(tmp_path.glob("*.partial"))
    assert first.read_bytes() == original
    package.read_backup(first, tmp_path / "restored.sqlite")
    pkg.close()


def test_references_are_portable_with_their_whole_backup_folder(tmp_path):
    pkg = _database(tmp_path)
    folder = tmp_path / "backups"
    folder.mkdir()
    ref = incremental.write(pkg.db_path, folder / "auto-20261029T010000Z.kbackup")
    moved = tmp_path / "moved"
    shutil.copytree(folder, moved)
    package.read_backup(moved / ref.name, tmp_path / "restored.sqlite")
    pkg.close()


def test_repository_symlink_is_never_written_or_used_for_collection(tmp_path):
    pkg = _database(tmp_path)
    victim = tmp_path / "outside.sqlite"
    victim.write_bytes(b"do not touch")
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / incremental.REPOSITORY).symlink_to(victim)
    ref = folder / "auto-20261029T010000Z.kbackup"
    with pytest.raises(incremental.BackupDataError) as error:
        incremental.write(pkg.db_path, ref)
    assert error.value.key == "error.backup.repository_symlink"
    with pytest.raises(incremental.BackupDataError) as error:
        incremental.collect(folder)
    assert error.value.key == "error.backup.repository_symlink"
    assert victim.read_bytes() == b"do not touch"
    assert not ref.exists()
    pkg.close()


def test_activity_starting_mid_copy_cancels_the_timer_without_acknowledgement(tmp_path,
                                                                           monkeypatch):
    pkg = _database(tmp_path)
    active = False
    real = priority.checkpoint

    def checkpoint(cancel=None, **kw):
        nonlocal active
        real(cancel, **kw)
        active = True

    monkeypatch.setattr(priority.GATE, "interactive", lambda: active)
    monkeypatch.setattr(priority, "checkpoint", checkpoint)
    ref = tmp_path / "auto-20261029T010000Z.kbackup"
    with pytest.raises(priority.CancelledError):
        incremental.write(pkg.db_path, ref, threading.Event(), quiet=True)
    assert not ref.exists()
    assert not list(tmp_path.glob("*.partial"))
    monkeypatch.undo()
    pkg.close()


def test_concurrent_manual_backups_do_not_race_or_overwrite(tmp_path):
    pkg = _database(tmp_path)
    pkg.history.commit("edit", ops.set_master(pkg.history.state, -5))
    now = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=2) as executor:
        copies = list(executor.map(lambda _: pkg.backup(now), range(2)))
    assert len(package.auto_backups(pkg.path / "backups")) == 1
    pkg.wait_compressed()
    available = pkg._made_copy()
    assert all(copy is not None for copy in copies)
    package.read_backup(available, tmp_path / "restored.sqlite")
    pkg.close()


def test_reusing_a_corrupt_chunk_never_acknowledges_a_new_backup(tmp_path):
    pkg = _database(tmp_path)
    first = incremental.write(pkg.db_path, tmp_path / "auto-20261029T010000Z.kbackup")
    db = sqlite3.connect(tmp_path / incremental.REPOSITORY)
    db.execute("update chunks set data=x'1234'")
    db.commit()
    db.close()
    second = tmp_path / "auto-20261029T011000Z.kbackup"
    with pytest.raises((ValueError, sqlite3.Error, incremental.zlib.error)):
        incremental.write(pkg.db_path, second)
    assert not second.exists()
    assert first.exists()
    pkg.close()
