"""File > Send a copy… (WP32 hand-off copy): the project with a choice of media.

Media is none / used parts plus 2 s handles / everything. The copy has a new copy id,
no locks, backups or caches, and finds its media again by SHA-256 on the other side.
"""

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import package, send_copy
from kuulas.messages import KuulasError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def noise(path: Path, seed: int, seconds: float) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.uniform(-0.5, 0.5, round(seconds * RATE))).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture(autouse=True)
def _private_media_prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


@pytest.fixture
def cut(session, tmp_path):
    """A 10 s recording of which the edit keeps only seconds 4 to 5."""
    (tmp_path / "audio").mkdir()
    source = noise(tmp_path / "audio" / "long.wav", 5, 10)
    session.import_media([str(source)])
    media_id = session.store.find(source)
    track = session.state.tracks[0].id
    session.edit("cut_range", {"track_ids": [track], "start": 5 * RATE, "end": 10 * RATE})
    session.edit("cut_range", {"track_ids": [track], "start": 0, "end": 4 * RATE})
    clip = session.state.tracks[0].clips[0]
    assert (clip.offset, clip.length) == (4 * RATE, RATE)
    return media_id, source


def receive(path: Path) -> Session:
    """Open the copy as the other person would. The decoded-audio cache is shared by
    every session of one process and keyed by media id, so it is emptied to stand in
    for the second machine."""
    other = Session(path)
    other.store.budget.discard_prefix("chunks", "m")
    return other


def test_none_copies_the_project_without_media(session, cut, tmp_path):
    media_id, source = cut
    report = session.send_copy(str(tmp_path / "out"), "none")
    source.rename(tmp_path / "gone.wav")  # the receiver does not have it where it was
    copy = Path(report["path"])
    assert copy.name == "Talk copy.kuulas"
    assert not list((copy / "media").glob("*.flac"))
    other = receive(copy)
    try:
        assert not other.read_only
        assert other.state == session.state
        assert other.store.missing() == [media_id]
    finally:
        other.close()


def test_copy_has_a_new_copy_id_and_no_locks_backups_or_caches(session, cut, tmp_path):
    session.store.peaks(cut[0])  # fills a cache
    session.package.backup()
    own = package.read_manifest(session.package.path)
    report = session.send_copy(str(tmp_path / "out"), "none")
    copy = Path(report["path"])
    manifest = package.read_manifest(copy)
    assert manifest["id"] == own["id"]
    assert manifest["copy"] != own["copy"]
    assert manifest["lineage"] == [*own["lineage"], own["copy"]]
    assert list((copy / "locks").iterdir()) == []
    assert list((copy / "backups").iterdir()) == []
    assert not any((copy / "caches").rglob("*.npy"))
    assert report["copy"] == manifest["copy"]


def test_copy_records_a_sent_checkpoint_in_the_senders_history(session, cut, tmp_path):
    report = session.send_copy(str(tmp_path / "out"), "none")
    sent = [c for c in session.history.checkpoints() if c["kind"] == "sent"]
    assert [c["copy"] for c in sent] == [report["copy"]]


def test_copy_forgets_the_senders_file_paths(session, cut, tmp_path):
    report = session.send_copy(str(tmp_path / "out"), "none")
    db = sqlite3.connect(Path(report["path"]) / "project.sqlite")
    try:
        assert db.execute("select count(*) from media_paths").fetchone()[0] == 0
    finally:
        db.close()


def test_a_second_copy_gets_its_own_folder(session, cut, tmp_path):
    first = session.send_copy(str(tmp_path / "out"), "none")["path"]
    second = session.send_copy(str(tmp_path / "out"), "none")["path"]
    assert first != second
    assert Path(first).is_dir()
    assert Path(second).is_dir()


def test_used_carries_the_used_part_with_two_second_handles(session, cut, tmp_path):
    media_id, source = cut
    full, _ = sf.read(source, dtype="float32")
    report = session.send_copy(str(tmp_path / "out"), "used")
    assert [c["id"] for c in report["carried"]] == [media_id]
    other = receive(Path(report["path"]))
    try:
        assert other.store.missing() == []
        # clip is seconds 4 to 5 of the source; handles make it 2 to 7
        inside = other.store.read(media_id, 2 * RATE, 5 * RATE)[0]
        assert np.allclose(inside, full[2 * RATE:7 * RATE], atol=1e-6)
        assert not np.any(other.store.read(media_id, 0, 2 * RATE - 1))
        assert not np.any(other.store.read(media_id, 7 * RATE + 1, 3 * RATE - 1))
        assert other.store.partial_ids() == [media_id]
    finally:
        other.close()


def test_used_copy_is_much_smaller_than_everything(session, cut, tmp_path):
    used = Path(session.send_copy(str(tmp_path / "u"), "used")["path"])
    everything = Path(session.send_copy(str(tmp_path / "a"), "all")["path"])

    def size(folder):
        return sum(f.stat().st_size for f in (folder / "media").rglob("*") if f.is_file())

    assert size(used) < size(everything) * 0.7


def test_locate_on_a_used_copy_swaps_in_the_whole_file(session, cut, tmp_path):
    media_id, source = cut
    full, _ = sf.read(source, dtype="float32")
    report = session.send_copy(str(tmp_path / "out"), "used")
    other = receive(Path(report["path"]))
    try:
        status = other.media_status()
        assert status["partial"] == [{"id": media_id, "name": "long.wav",
                                      "can_complete": True}]
        answer = other.locate_media(str(source.parent))
        assert [f["id"] for f in answer["found"]] == [media_id]
        assert answer["partial"] == []
        assert other.store.partial_ids() == []
        assert other.store.is_linked(media_id)
        assert not other.store.working_file(media_id).exists()
        assert np.allclose(other.store.read(media_id, 0, 3 * RATE)[0], full[:3 * RATE],
                           atol=1e-6)
    finally:
        other.close()


def test_locate_does_not_take_a_wrong_file_for_a_used_copy(session, cut, tmp_path):
    media_id, _source = cut
    report = session.send_copy(str(tmp_path / "out"), "used")
    other = receive(Path(report["path"]))
    try:
        wrong = tmp_path / "wrong"
        wrong.mkdir()
        noise(wrong / "long.wav", 77, 10)  # same size, other content
        answer = other.locate_media(str(wrong))
        assert answer["found"] == []
        assert other.store.partial_ids() == [media_id]
    finally:
        other.close()


def test_none_copy_relinks_by_hash_from_the_receivers_own_files(session, cut, tmp_path):
    media_id, source = cut
    report = session.send_copy(str(tmp_path / "out"), "none")
    receivers = tmp_path / "receiver"
    receivers.mkdir()
    source.rename(receivers / "mine.wav")
    other = receive(Path(report["path"]))
    try:
        answer = other.locate_media(str(receivers))
        assert [f["id"] for f in answer["found"]] == [media_id]
        assert other.store.missing() == []
    finally:
        other.close()


def test_all_carries_the_linked_files_into_the_copy(session, cut, tmp_path):
    media_id, source = cut
    report = session.send_copy(str(tmp_path / "out"), "all")
    source.unlink()
    other = receive(Path(report["path"]))
    try:
        other.store.wait_for_resolution(timeout=5)
        assert other.store.missing() == []
        assert other.store.partial_ids() == []
        assert np.any(other.store.read(media_id, 4 * RATE, RATE))
    finally:
        other.close()


def test_working_media_travels_whole_in_none_mode(session, tmp_path):
    source = noise(tmp_path / "c.wav", 3, 2)
    session.import_media([str(source)], copy=True)  # stored as the project's own FLAC
    media_id = session.state.media[0].id
    assert not session.store.is_linked(media_id)
    report = session.send_copy(str(tmp_path / "out"), "none")
    assert [c["id"] for c in report["carried"]] == [media_id]
    other = receive(Path(report["path"]))
    try:
        assert other.store.missing() == []
        assert np.any(other.store.read(media_id, 0, RATE))
    finally:
        other.close()


def test_offline_media_is_reported_not_faked(session, cut, tmp_path):
    media_id, source = cut
    source.unlink()
    report = session.send_copy(str(tmp_path / "out"), "used")
    assert [u["id"] for u in report["unavailable"]] == [media_id]
    assert report["carried"] == []


def test_a_bad_choice_or_folder_is_refused(session, cut, tmp_path):
    with pytest.raises(KuulasError) as caught:
        session.send_copy(str(tmp_path / "out"), "some")
    assert caught.value.key == "error.send_copy.bad_media"
    with pytest.raises(KuulasError) as caught:
        session.send_copy("", "none")
    assert caught.value.key == "error.send_copy.no_folder"


def test_plan_estimates_each_choice(session, cut):
    plan = session.send_copy_plan()
    assert plan["none"]["bytes"] == 0
    assert 0 < plan["used"]["bytes"] < plan["all"]["bytes"]
    assert plan["used"]["seconds"] == pytest.approx(5.0)  # clip 4 to 5 plus 2 s each side
    assert plan["handle_seconds"] == 2.0


def test_used_ranges_merge_and_stay_inside_the_media(session, cut):
    media_id, _ = cut
    ranges = send_copy.used_ranges(session.state, {media_id: 10 * RATE}, 2.0)
    assert ranges == {media_id: ((2 * RATE, 7 * RATE),)}
    near_start = send_copy.used_ranges(session.state, {media_id: 6 * RATE}, 2.0)
    assert near_start == {media_id: ((2 * RATE, 6 * RATE),)}


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()

    class Engine:
        def status(self):
            return {"playing": False, "position": 0, "until": None, "notices": []}

        def close(self):
            pass

    with TestClient(create_app(session, Engine(), language="en", ui_dir=ui)) as c:
        yield c


def test_api_plan_and_send(client, session, cut, tmp_path):
    plan = client.get("/api/send-copy/plan").json()
    assert set(plan) >= {"none", "used", "all", "handle_seconds"}
    answer = client.post("/api/send-copy", json={"folder": str(tmp_path / "out"),
                                                   "media": "used"})
    assert answer.status_code == 200
    body = answer.json()
    assert Path(body["path"]).is_dir()
    manifest = json.loads((Path(body["path"]) / "manifest.json").read_text())
    assert manifest["copy"] == body["copy"]


def test_api_send_bad_choice_is_400(client, cut, tmp_path):
    answer = client.post("/api/send-copy", json={"folder": str(tmp_path), "media": "x"})
    assert answer.status_code == 400
    assert answer.json()["error"]["key"] == "error.send_copy.bad_media"
