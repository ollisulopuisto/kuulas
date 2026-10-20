"""Mod+S (save_backup) and Shift+Mod+S (save_checkpoint): the server side.

Every edit is already committed, so "save" makes a backup copy now and a
named checkpoint marks the step; neither changes the project.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from kuulas import package
from kuulas.server import create_app
from kuulas.session import Session


class _Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


def _client(session: Session) -> TestClient:
    return TestClient(create_app(session, _Engine(), language="en"))


def _autos(session: Session) -> list:
    """One file per automatic backup, plain or xz (compressed in the background)."""
    return sorted(paths[0] for _when, paths
                  in package.auto_backups(session.package.path / "backups"))


def test_save_backup_writes_a_backup_file_now(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        assert _autos(s) == []
        r = _client(s).post("/api/command", json={"name": "save_backup", "args": {}})
        assert r.status_code == 200
        files = _autos(s)
        assert len(files) == 1
        assert files[0].name.startswith(r.json()["backup"])
    finally:
        s.close()


def test_save_backup_keeps_to_the_retention_rule(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        folder = s.package.path / "backups"
        folder.mkdir(exist_ok=True)
        base = datetime.now(UTC) - timedelta(minutes=5)
        for i in range(20):
            stamp = (base - timedelta(seconds=i)).strftime("%Y%m%dT%H%M%SZ")
            (folder / f"auto-{stamp}.sqlite").write_bytes(b"x")
        _client(s).post("/api/command", json={"name": "save_backup", "args": {}})
        assert len(_autos(s)) <= package.KEEP_RECENT
    finally:
        s.close()


def test_save_backup_on_a_nearly_full_disk_says_none_was_made(tmp_path, monkeypatch):
    s = Session(tmp_path / "One.kuulas")
    try:
        class Usage:
            total = used = free = 0

        monkeypatch.setattr(package.shutil, "disk_usage", lambda _p: Usage)
        r = _client(s).post("/api/command", json={"name": "save_backup", "args": {}})
        assert r.status_code == 400
        assert r.json()["error"]["key"] == "error.package.backup_low_disk"
        assert _autos(s) == []
    finally:
        s.close()


def test_save_checkpoint_names_the_current_step(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        r = _client(s).post("/api/command", json={
            "name": "save_checkpoint", "args": {"name": "Saved 14.05"}})
        assert r.status_code == 200
        assert [c["name"] for c in s.history.checkpoints()] == ["Saved 14.05"]
    finally:
        s.close()


def _read_only(tmp_path) -> Session:
    pkg = package.create(tmp_path / "A.kuulas")
    pkg.close()
    beat = (datetime.now(UTC) - timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (pkg.path / "lock.json").write_text(json.dumps({
        "host": "windows-pc", "pid": 4242, "user": "ville",
        "opened_utc": beat, "heartbeat_utc": beat}))
    return Session(pkg.path)


def test_read_only_project_says_so_and_writes_nothing(tmp_path):
    s = _read_only(tmp_path)
    try:
        assert s.read_only
        client = _client(s)
        for name, args in (("save_backup", {}), ("save_checkpoint", {"name": "x"})):
            r = client.post("/api/command", json={"name": name, "args": args})
            assert r.status_code == 400, name
            assert "windows-pc" in json.dumps(r.json()), name
        assert _autos(s) == []
        assert s.history.checkpoints() == []
    finally:
        s.close()
