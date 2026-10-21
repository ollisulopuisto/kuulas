"""Series commands on an open project and their routes (docs/design/SERIES.md):
save as series defaults, apply (one undo step), choose/detach, new episode, and the
series music (references only: no recorded file is ever copied, moved or changed)."""

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine, wav

from kuulas import automix, messages, ops, series_actions, series_settings
from kuulas.series_library import SeriesLibrary, SeriesLibraryError
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture(autouse=True)
def _private_files(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_SERIES_DIR", str(tmp_path / "series"))
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Ep 1.kuulas")
    yield s
    s.close()


def _layout(s: Session) -> None:
    p = ops.add_bus(s.state, "b1", "Voices")
    p = ops.set_bus(p, "b1", kind="speech")
    p = ops.add_track(p, "t1", "Olli", bus="b1")
    p = ops.set_track(p, "t1", gain_db=-3.0)
    p = ops.add_track(p, "t2", "Music", kind="music")
    with s.lock:
        s.history.commit("setup", p)


def test_save_creates_a_series_and_links_the_project_with_its_copy(session):
    _layout(session)
    automix.save_settings({"options": {"speech_debleed": False}})
    out = series_actions.save_defaults(session, name="Vikasietotila",
                                       auto_silence={"margin_db": 8})
    link = session.state.series
    assert link["name"] == "Vikasietotila"
    record = SeriesLibrary().load(link["id"])
    assert record["settings"]["layout"]["tracks"][0]["name"] == "Olli"
    assert record["settings"]["auto_silence"]["margin_db"] == 8.0
    assert record["settings"]["automix"]["speech_debleed"] is False
    assert link["settings"] == record["settings"]  # the project's own copy
    assert out["differs"] == []
    assert out["found"] is True


def test_save_needs_a_name_for_a_new_series(session):
    with pytest.raises(SeriesLibraryError):
        series_actions.save_defaults(session, name="  ")


def test_status_says_what_differs_and_apply_brings_it_back_in_one_undo_step(session):
    _layout(session)
    series_actions.save_defaults(session, name="Show", auto_silence={"margin_db": 8})
    with session.lock:
        session.history.commit("louder", ops.set_track(session.state, "t1", gain_db=2.0))
    automix.save_settings({"options": {"speech_rider": False}})
    status = series_actions.status(session, auto_silence={"margin_db": 12})
    assert status["differs"] == ["layout", "auto_silence", "automix"]
    out = series_actions.apply(session)
    assert session.state.track("t1").gain_db == -3.0
    assert out["settings"]["auto_silence"]["margin_db"] == 8.0
    assert automix.load_settings().get("options", {}).get("speech_rider", True) is True
    assert series_actions.status(session, auto_silence={"margin_db": 8})["differs"] == []
    session.undo()
    assert session.state.track("t1").gain_db == 2.0


def test_apply_without_the_series_file_is_a_clear_error_and_changes_nothing(session):
    _layout(session)
    series_actions.save_defaults(session, name="Show")
    sid = session.state.series["id"]
    (SeriesLibrary().folder / f"{sid}.json").unlink()
    before = session.state
    with pytest.raises(SeriesLibraryError) as raised:
        series_actions.apply(session)
    assert raised.value.key == "error.series.missing"
    assert session.state == before
    status = series_actions.status(session)
    assert status["found"] is False
    assert status["link"]["name"] == "Show"  # the project keeps its copy
    # Saving again brings the file back under the same id.
    series_actions.save_defaults(session)
    assert SeriesLibrary().load(sid)["name"] == "Show"


def test_attach_detach_and_rename(session):
    record = SeriesLibrary().create("Other", {"layout": {"tracks": [{"name": "Host"}]}})
    series_actions.attach(session, record["id"])
    assert session.state.series["id"] == record["id"]
    assert session.state.tracks == ()  # attaching applies nothing
    assert series_actions.status(session)["differs"] == ["layout"]
    series_actions.rename(session, "Other show")
    assert SeriesLibrary().load(record["id"])["name"] == "Other show"
    assert session.state.series["name"] == "Other show"
    series_actions.detach(session)
    assert session.state.series == {}
    assert SeriesLibrary().load(record["id"]) is not None  # the series stays


def test_new_episode_starts_with_the_series_layout(session, tmp_path):
    _layout(session)
    series_actions.save_defaults(session, name="Show")
    sid = session.state.series["id"]
    folder = series_actions.new_episode(str(tmp_path), "Ep 2", sid)
    assert folder == tmp_path / "Ep 2.kuulas"
    other = Session(folder)
    try:
        assert [t.name for t in other.state.tracks] == ["Olli", "Music"]
        assert other.state.series["id"] == sid
        assert series_settings.differences(
            {"layout": series_settings.layout_of(other.state)},
            {"layout": other.state.series["settings"]["layout"]}) == []
    finally:
        other.close()


def test_series_music_is_references_and_places_on_a_new_episode(session, tmp_path):
    path = wav(tmp_path / "intro.wav")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    before = path.read_bytes()
    session.import_media([str(path)], copy=False)
    clip = session.state.tracks[0].clips[0]
    with pytest.raises(SeriesLibraryError):  # no series yet
        series_actions.music_add(session, [clip.id], "Intro")
    series_actions.save_defaults(session, name="Show")
    out = series_actions.music_add(session, [clip.id], "Intro")
    assert out["music"] == 1
    record = SeriesLibrary().load(session.state.series["id"])
    assert record["music"]["entries"][0]["refs"][0]["media_sha256"] == digest
    assert str(path.resolve()) in record["media"][digest]["paths"]

    folder = series_actions.new_episode(str(tmp_path), "Ep 2", record["id"])
    other = Session(folder)
    try:
        report = series_actions.music_place(other)
        assert report["placed"] == 1
        assert report["missing"] == []
        placed = [c for t in other.state.tracks for c in t.clips]
        assert len(placed) == 1
        assert placed[0].start == clip.start
        other.undo()
        assert [c for t in other.state.tracks for c in t.clips] == []
        assert series_actions.music_to_clipboard(other)["added"] == 1
        assert len(other.clipboard.load().entries()) == 1
    finally:
        other.close()
    assert path.read_bytes() == before  # the recording is untouched


def test_place_reports_a_recording_that_cannot_be_found(session, tmp_path):
    path = wav(tmp_path / "jingle.wav")
    session.import_media([str(path)], copy=False)
    series_actions.save_defaults(session, name="Show")
    series_actions.music_add(session, [session.state.tracks[0].clips[0].id], "Jingle")
    sid = session.state.series["id"]
    record = SeriesLibrary().load(sid)
    SeriesLibrary().update(sid, media={})
    entries = record["music"]["entries"]
    entries[0]["source_project"] = ""
    SeriesLibrary().update(sid, music={"entries": entries})
    folder = series_actions.new_episode(str(tmp_path), "Ep 3", sid)
    other = Session(folder)
    try:
        report = series_actions.music_place(other)
        assert report["placed"] == 0
        assert len(report["missing"]) == 1
    finally:
        other.close()


# -- routes ---------------------------------------------------------------------


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, FakeEngine(), language="en", ui_dir=ui)) as c:
        yield c


def test_routes_save_status_apply_detach(client, session):
    _layout(session)
    r = client.post("/api/series/save", json={"name": "Show",
                                             "auto_silence": {"margin_db": 7}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["series"]["link"]["name"] == "Show"
    assert body["project"]["series"]["name"] == "Show"
    r = client.post("/api/series/status", json={"auto_silence": {"margin_db": 9}})
    assert r.json()["differs"] == ["auto_silence"]
    assert [s["name"] for s in r.json()["list"]] == ["Show"]
    r = client.post("/api/series/apply", json={})
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["auto_silence"]["margin_db"] == 7.0
    r = client.post("/api/series/detach", json={})
    assert r.json()["project"].get("series") is None


def test_route_errors_are_messages(client):
    r = client.post("/api/series/apply", json={})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.series.none"
    r = client.post("/api/series/attach", json={"series_id": "../x"})
    assert r.status_code == 400
    assert json.dumps(r.json())
