"""The clipboard per project (WP65 step 1): ``<project>.kuulas/clipboard.json``."""

import json
import logging
import os
import socket
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas.clipboard import ClipboardHistory, ClipRef, Entry
from kuulas.clipboard_store import ClipboardStore, default_path
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def wav(path: Path, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


def entry(n: int, pinned: bool = False) -> Entry:
    return Entry(f"e{n:04d}", f"name {n}", float(n), refs=(ClipRef("a" * 64, 0, 100),),
                 span=(0, 100), pinned=pinned)


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    yield s
    s.close()


def first_clip(s):
    return s.state.tracks[0].clips[0].id


# -- the store -----------------------------------------------------------------


def test_the_store_has_no_cap_and_drops_nothing(tmp_path):
    store = ClipboardStore(tmp_path / "clipboard.json")
    for n in range(130):
        store.update(lambda h, n=n: h.add(entry(n)))
    assert len(ClipboardStore(tmp_path / "clipboard.json").load().entries()) == 130


def test_prune_to_the_newest_keeps_that_many():
    h = ClipboardHistory()
    for n in range(10):
        h.add(entry(n))
    assert h.prune(4) == 6
    assert [e.id for e in h.entries()] == ["e0009", "e0008", "e0007", "e0006"]
    assert h.prune(4) == 0


def test_a_store_that_may_not_write_keeps_entries_in_memory_only(tmp_path):
    path = tmp_path / "clipboard.json"
    ClipboardStore(path).update(lambda h: h.add(entry(1)))
    before = path.read_bytes()
    ro = ClipboardStore(path, writable=False)
    ro.update(lambda h: h.add(entry(2)))
    assert path.read_bytes() == before  # nothing written
    assert [e.id for e in ro.load().entries()] == ["e0002", "e0001"]  # but usable
    assert [e.id for e in ClipboardStore(path).load().entries()] == ["e0001"]


def test_a_soft_store_logs_a_failed_write_and_does_not_raise(
        tmp_path, caplog, monkeypatch):
    store = ClipboardStore(tmp_path / "clipboard.json", soft=True)

    def boom(self, text):
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(ClipboardStore, "_write", boom)
        with caplog.at_level(logging.WARNING):
            assert store.update(lambda h: h.add(entry(1))) is None
        assert caplog.records
        assert "disk full" in store.write_error
    store.update(lambda h: h.add(entry(2)))
    assert store.write_error is None


# -- the session ---------------------------------------------------------------


def test_a_copy_goes_to_the_project_folder_not_the_user_file(session):
    session.clipboard_copy(clip_ids=[first_clip(session)])
    assert (session.package.path / "clipboard.json").is_file()
    assert not default_path().exists()
    assert len(session.clipboard_list()) == 1


def test_another_project_does_not_see_it(tmp_path, session):
    saved = session.clipboard_copy(clip_ids=[first_clip(session)], name="Anna")["entry"]
    other = Session(tmp_path / "Two.kuulas")
    try:
        assert other.clipboard_list() == []
    finally:
        other.close()
    path = session.package.path / "clipboard.json"
    assert json.loads(path.read_text())["entries"][0]["id"] == saved["id"]


def test_a_reopened_project_has_its_entries(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    saved = s.clipboard_copy(clip_ids=[s.state.tracks[0].clips[0].id])["entry"]
    s.close()
    again = Session(tmp_path / "One.kuulas")
    try:
        assert [e["id"] for e in again.clipboard_list()] == [saved["id"]]
    finally:
        again.close()


def test_the_clipboard_is_not_project_state(session):
    nodes = len(session.history.nodes())
    state = session.state
    session.clipboard_copy(clip_ids=[first_clip(session)])
    session.clipboard_rename(session.clipboard_list()[0]["id"], "x")
    assert len(session.history.nodes()) == nodes
    assert session.state == state


def test_a_conflicted_copy_is_never_read(session):
    session.clipboard_copy(clip_ids=[first_clip(session)], name="mine")
    good = (session.package.path / "clipboard.json").read_text()
    (session.package.path / "clipboard (conflicted copy).json").write_text(
        good.replace('"mine"', '"theirs"'))
    assert [e["name"] for e in session.clipboard_list()] == ["mine"]


def test_no_prune_on_copy_120_entries_stay(session):
    clip = first_clip(session)
    for _ in range(120):
        session.clipboard_copy(clip_ids=[clip])
    assert len(session.clipboard_list()) == 120


def test_clear_old_entries_keeps_the_newest_hundred_by_default(session):
    clip = first_clip(session)
    ids = [session.clipboard_copy(clip_ids=[clip])["entry"]["id"] for _ in range(130)]
    assert session.clipboard_clear_old() == 30
    assert [e["id"] for e in session.clipboard_list()] == ids[::-1][:100]
    assert session.clipboard_clear_old(10) == 90
    assert len(session.clipboard_list()) == 10


def test_a_read_only_open_never_writes_the_clipboard(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    (own,) = (s.package.path / "locks").glob("*.json")
    lock = json.loads(own.read_text())
    (s.package.path / "locks" / "other.json").write_text(json.dumps({
        **lock, "instance": "other", "host": socket.gethostname(), "pid": os.getppid()}))
    second = Session(tmp_path / "One.kuulas")
    try:
        assert second.read_only
        second.clipboard_copy(clip_ids=[second.state.tracks[0].clips[0].id])
        assert not (s.package.path / "clipboard.json").exists()
        assert len(second.clipboard_list()) == 1  # usable for this window
    finally:
        second.close()
        s.close()


class _Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


def test_api_clear_old_entries(session, tmp_path):
    clip = first_clip(session)
    for _ in range(5):
        session.clipboard_copy(clip_ids=[clip])
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _Engine(), language="en", ui_dir=ui)) as client:
        check_clear_old(client)


def check_clear_old(client):
    r = client.post("/api/clipboard/clear-old", json={"keep": 2})
    assert r.status_code == 200
    assert r.json()["removed"] == 3
    assert len(r.json()["entries"]) == 2
    r = client.post("/api/clipboard/clear-old", json={})
    assert r.json()["removed"] == 0
