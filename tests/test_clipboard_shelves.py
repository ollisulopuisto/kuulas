"""The clipboard's shelves (docs/design/CLIPBOARD-SHELVES.md): this project, the series
(the series file's music list) and shared. Moving between shelves copies; duplicates are
refused; no recorded file is ever copied, moved or changed (rule 17)."""

from __future__ import annotations

import hashlib
import shutil

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine, wav

from kuulas import messages, ops, series_actions
from kuulas.clipboard import ClipRef, Entry, same_content
from kuulas.series_library import SeriesLibrary, SeriesLibraryError
from kuulas.server import create_app
from kuulas.session import NoSuchEntryError, Session


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


def _copied(session, tmp_path, name="intro.wav"):
    """A recording imported in place and copied to the project shelf: (path, entry id)."""
    path = wav(tmp_path / name)
    session.import_media([str(path)], copy=False)
    clip = session.state.tracks[0].clips[0]
    entry = session.clipboard_copy(clip_ids=[clip.id])["entry"]
    return path, entry["id"]


# -- pure ---------------------------------------------------------------------------


def test_same_content_is_the_same_id_or_the_same_references_and_length():
    ref = ClipRef("a" * 64, 0, 100)
    a = Entry("1", "", 0.0, refs=(ref,), span=(0, 100))
    assert same_content(a, Entry("1", "x", 5.0))
    assert same_content(a, Entry("2", "other", 9.0, refs=(ref,), span=(500, 600)))
    assert not same_content(a, Entry("2", "", 0.0, refs=(ref,), span=(0, 90)))
    other = ClipRef("b" * 64, 0, 100)
    assert not same_content(a, Entry("2", "", 0.0, refs=(other,), span=(0, 100)))


# -- the series shelf ---------------------------------------------------------------


def test_no_series_is_an_empty_shelf_and_adding_is_an_error(session, tmp_path):
    _path, entry_id = _copied(session, tmp_path)
    shelf = series_actions.shelf_list(session)
    assert shelf == {"link": None, "found": False, "entries": []}
    with pytest.raises(SeriesLibraryError) as e:
        series_actions.shelf_add(session, entry_id)
    assert e.value.key == "error.series.none"


def test_add_copies_the_entry_with_its_id_and_where_its_recording_is(session, tmp_path):
    path, entry_id = _copied(session, tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    series_actions.save_defaults(session, name="Show")
    shelf = series_actions.shelf_add(session, entry_id)
    assert [e["id"] for e in shelf["entries"]] == [entry_id]
    assert shelf["entries"][0]["missing_here"] == 0
    record = SeriesLibrary().load(session.state.series["id"])
    assert str(path.resolve()) in record["media"][digest]["paths"]
    # A copy: the project's own entry stays.
    assert session.clipboard.load().get(entry_id) is not None
    # The same entry again, or the same content under another id: refused.
    with pytest.raises(ops.EditError) as e:
        series_actions.shelf_add(session, entry_id)
    assert e.value.key == "error.clipboard.already_on_shelf"
    clip = session.state.tracks[0].clips[0]
    twin = session.clipboard_copy(clip_ids=[clip.id])["entry"]["id"]
    with pytest.raises(ops.EditError):
        series_actions.shelf_add(session, twin)
    with pytest.raises(NoSuchEntryError):
        series_actions.shelf_add(session, "nope")


def test_series_music_commands_work_on_the_shelf(session, tmp_path):
    _path, entry_id = _copied(session, tmp_path)
    series_actions.save_defaults(session, name="Show")
    series_actions.shelf_add(session, entry_id)
    assert series_actions.status(session)["music"] == 1
    folder = series_actions.new_episode(str(tmp_path), "Ep 2", session.state.series["id"])
    other = Session(folder)
    try:
        assert series_actions.music_place(other)["placed"] == 1
        assert series_actions.shelf_list(other)["entries"][0]["id"] == entry_id
    finally:
        other.close()


def test_remove_takes_the_reference_off_and_never_the_recording(session, tmp_path):
    path, entry_id = _copied(session, tmp_path)
    before = path.read_bytes()
    series_actions.save_defaults(session, name="Show")
    series_actions.shelf_add(session, entry_id)
    shelf = series_actions.shelf_remove(session, entry_id)
    assert shelf["entries"] == []
    record = SeriesLibrary().load(session.state.series["id"])
    assert record["media"] == {}  # no entry uses it any more
    assert path.read_bytes() == before
    assert session.clipboard.load().get(entry_id) is not None
    with pytest.raises(NoSuchEntryError):
        series_actions.shelf_remove(session, entry_id)


def test_adopt_links_the_recording_from_the_series_paths_and_pastes(session, tmp_path):
    path, entry_id = _copied(session, tmp_path)
    before = path.read_bytes()
    series_actions.save_defaults(session, name="Show")
    series_actions.shelf_add(session, entry_id)
    sid = session.state.series["id"]
    # The source project is gone: only the series' own paths can find the recording.
    session.close()
    shutil.rmtree(tmp_path / "Ep 1.kuulas")
    folder = series_actions.new_episode(str(tmp_path), "Ep 2", sid)
    other = Session(folder)
    try:
        view = series_actions.shelf_adopt(other, entry_id)
        assert view["id"] != entry_id
        assert view["missing_here"] == 0
        report = other.clipboard_paste(view["id"], at=0)
        assert report["placed"] == 1
        assert report["missing"] == []
        with pytest.raises(NoSuchEntryError):
            series_actions.shelf_adopt(other, "nope")
    finally:
        other.close()
    assert path.read_bytes() == before


# -- the shared shelf ---------------------------------------------------------------


def test_sharing_the_same_content_twice_is_refused(session, tmp_path):
    _path, first = _copied(session, tmp_path)
    clip = session.state.tracks[0].clips[0]
    second = session.clipboard_copy(clip_ids=[clip.id])["entry"]["id"]
    session.clipboard_share(first, True)
    with pytest.raises(ops.EditError) as e:
        session.clipboard_share(second, True)
    assert e.value.key == "error.clipboard.already_on_shelf"
    session.clipboard_share(first, True)  # the same one again stays fine


# -- routes -------------------------------------------------------------------------


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, FakeEngine(), language="en", ui_dir=ui)) as c:
        yield c


def test_routes(client, session, tmp_path):
    _path, entry_id = _copied(session, tmp_path)
    r = client.get("/api/series/shelf")
    assert r.json() == {"link": None, "found": False, "entries": []}
    r = client.post("/api/series/shelf/add", json={"entry_id": entry_id})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.series.none"
    series_actions.save_defaults(session, name="Show")
    r = client.post("/api/series/shelf/add", json={"entry_id": entry_id})
    assert r.status_code == 200, r.text
    assert [e["id"] for e in r.json()["entries"]] == [entry_id]
    assert r.json()["link"]["name"] == "Show"
    r = client.post("/api/series/shelf/adopt", json={"entry_id": entry_id})
    assert r.status_code == 200, r.text
    assert len(r.json()["entries"]) == 2  # the project shelf, with the adopted copy
    r = client.post("/api/series/shelf/remove", json={"entry_id": entry_id})
    assert r.json()["entries"] == []
    r = client.post("/api/series/shelf/remove", json={"entry_id": entry_id})
    assert r.status_code == 404
