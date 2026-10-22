"""Mod+S and Shift+Mod+S (save_checkpoint) and File > Back up now (save_backup):
the server side.

Every edit is already committed, so "save" marks the current step as a saved
version (a checkpoint); it makes none when that step already is one. The backup
copy is its own command (``save_backup``: File > Back up now and the timer).
Neither changes the project.
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


def _save(client, name, **args):
    r = client.post("/api/command", json={
        "name": "save_checkpoint", "args": {"name": name, **args}})
    assert r.status_code == 200, r.text
    return r.json()["saved"]


def test_saving_twice_on_the_same_step_makes_one_version_and_says_already(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        client = _client(s)
        first = _save(client, "Saved 14.32")
        assert first["result"] == "made"
        assert first["name"] == "Saved 14.32"
        assert first["created"]
        again = _save(client, "Saved 14.33")
        assert again["result"] == "already"
        assert again["name"] == "Saved 14.32"
        assert again["created"] == first["created"]
        assert [c["name"] for c in s.history.checkpoints()] == ["Saved 14.32"]
    finally:
        s.close()


def test_saving_after_an_edit_makes_a_new_version(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        client = _client(s)
        _save(client, "Saved 14.32")
        s.edit("add_track", {"name": "A"})
        made = _save(client, "Saved 14.40")
        assert made["result"] == "made"
        names = [c["name"] for c in s.history.checkpoints()]
        assert names == ["Saved 14.32", "Saved 14.40"]
    finally:
        s.close()


def test_saving_never_overwrites_a_sent_copys_version(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        s.checkpoint("v1 sent to Ville", "sent")
        r = _save(_client(s), "Saved 14.32")
        assert r["result"] == "already"
        assert [(c["name"], c["kind"]) for c in s.history.checkpoints()] == [
            ("v1 sent to Ville", "sent")]
    finally:
        s.close()


def test_a_new_name_on_a_saved_step_renames_it_the_same_name_does_not(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        client = _client(s)
        _save(client, "Saved 14.32")
        renamed = _save(client, "Before the interview", rename=True)
        assert renamed["result"] == "renamed"
        assert renamed["name"] == "Before the interview"
        same = _save(client, "Before the interview", rename=True)
        assert same["result"] == "already"
        assert [(c["name"], c["kind"]) for c in s.history.checkpoints()] == [
            ("Before the interview", "manual")]
    finally:
        s.close()


def test_save_answers_the_step_so_the_toast_can_offer_rename(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    try:
        saved = _save(_client(s), "Saved 14.32")
        assert saved["node"] == s.history.head
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
