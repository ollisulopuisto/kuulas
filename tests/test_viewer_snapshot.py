"""No writes to the source, including SQLite WAL/SHM sidecar creation."""
import hashlib
import importlib.util
import sqlite3
from pathlib import Path

import pytest

from kuulas import ops, package

MODULE = Path(__file__).resolve().parents[1] / 'viewer' / 'Tools' / 'snapshot.py'
spec = importlib.util.spec_from_file_location('viewer_snapshot', MODULE)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_closed_project_snapshot_creates_no_source_sidecars(tmp_path):
    source = tmp_path / 'Closed.kuulas'
    p = package.create(source)
    p.close()
    before = tree(source)
    with reader.snapshot(source) as db:
        assert db.execute('select count(*) from edits').fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError):
            db.execute("update meta set value='wrong'")
    assert tree(source) == before


def test_snapshot_reads_committed_live_wal_without_checkpoint_or_lock(tmp_path):
    source = tmp_path / 'Live.kuulas'
    p = package.create(source)
    try:
        p.history.commit('In WAL', ops.set_master(p.history.state, -7))
        head = p.history.head
        assert (source / 'project.sqlite-wal').stat().st_size > 0
        before = tree(source)
        with reader.snapshot(source) as db:
            row = db.execute("select head from edits where id='main'").fetchone()
            assert row == (head,)
        assert tree(source) == before
    finally:
        p.close()


def test_changed_source_during_copy_is_rejected(tmp_path, monkeypatch):
    source = tmp_path / 'Moving.kuulas'
    p = package.create(source)
    try:
        real_copy = reader.shutil.copyfile

        def changing_copy(src, dest):
            result = real_copy(src, dest)
            if src.name == 'project.sqlite':
                p.history.commit('Raced', ops.set_master(p.history.state, -9))
            return result

        monkeypatch.setattr(reader.shutil, 'copyfile', changing_copy)
        with pytest.raises(reader.UnstableSnapshotError), reader.snapshot(source):
            pytest.fail('A torn snapshot was accepted')
    finally:
        p.close()
