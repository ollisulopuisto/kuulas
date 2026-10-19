"""Looking into other projects' clipboards, and adopting from them (WP65 step 5)."""

import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import clipboard_browse, desktop
from kuulas.clipboard import ClipRef, Entry
from kuulas.clipboard_store import ClipboardStore, project_path
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def wav(path, seed):
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


def entry(n, source="", name=None, **over):
    return Entry(f"e{n:04d}", name or f"name {n}", float(n),
                 refs=(ClipRef("a" * 64, 0, 100),), span=(0, 100),
                 source_project=source, **over)


def make_project(tmp_path, name, *entries):
    """A closed project with these entries on its clipboard."""
    folder = tmp_path / f"{name}.kuulas"
    Session(folder).close()
    store = ClipboardStore(project_path(folder))
    for item in entries:
        store.update(lambda h, item=item: h.add(item))
    return folder


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Here.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1))])
    yield s
    s.close()


# -- the path rule -------------------------------------------------------------


def test_a_real_project_folder_is_accepted(tmp_path):
    folder = make_project(tmp_path, "Other")
    assert clipboard_browse.project_folder(str(folder)) == folder.resolve()


@pytest.mark.parametrize("bad", [
    "", "   ", "relative/Other.kuulas", "Other.kuulas", "~/Other.kuulas", None, 5, ["x"],
    "/a/b\0c.kuulas",
])
def test_paths_that_are_not_absolute_text_are_refused(bad):
    with pytest.raises(EditError) as e:
        clipboard_browse.project_folder(bad)
    assert e.value.key == "error.clipboard.bad_project"


def test_traversal_is_refused_even_when_it_would_land_on_a_project(tmp_path):
    folder = make_project(tmp_path, "Other")
    (tmp_path / "sub").mkdir()
    sneaky = f"{tmp_path}/sub/../{folder.name}"
    with pytest.raises(EditError):
        clipboard_browse.project_folder(sneaky)


def test_only_existing_kuulas_folders_with_a_manifest_count(tmp_path):
    plain = tmp_path / "Plain"
    plain.mkdir()
    empty = tmp_path / "Empty.kuulas"
    empty.mkdir()  # no manifest.json: not a project
    a_file = tmp_path / "File.kuulas"
    a_file.write_text("x")
    for bad in (plain, empty, a_file, tmp_path / "Missing.kuulas", tmp_path):
        with pytest.raises(EditError):
            clipboard_browse.project_folder(str(bad))


def test_a_link_that_lands_outside_a_project_is_refused(tmp_path):
    plain = tmp_path / "Plain"
    plain.mkdir()
    link = tmp_path / "Looks.kuulas"
    link.symlink_to(plain)
    with pytest.raises(EditError):
        clipboard_browse.project_folder(str(link))


# -- reading -------------------------------------------------------------------


def test_a_clipboard_is_read_without_touching_the_project(tmp_path):
    folder = make_project(tmp_path, "Other", entry(1), entry(2))

    def snapshot():
        return sorted((str(p.relative_to(folder)), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in folder.rglob("*") if p.is_file())

    before = snapshot()
    got = clipboard_browse.read_entries(folder)
    assert [e.id for e in got] == ["e0002", "e0001"]
    assert snapshot() == before  # not one byte written, no lock file, no database change


def test_it_reads_a_project_that_is_open_elsewhere_without_taking_its_lock(
        tmp_path, session):
    session.clipboard_copy(clip_ids=[session.state.tracks[0].clips[0].id])
    locks = sorted(p.name for p in (session.package.path / "locks").iterdir())
    got = clipboard_browse.read_entries(session.package.path)
    assert len(got) == 1
    assert sorted(p.name for p in (session.package.path / "locks").iterdir()) == locks


def test_it_never_opens_the_database(tmp_path):
    folder = make_project(tmp_path, "Other", entry(1))
    (folder / "project.sqlite").unlink()
    for side in folder.glob("project.sqlite-*"):
        side.unlink()
    assert [e.id for e in clipboard_browse.read_entries(folder)] == ["e0001"]
    assert not (folder / "project.sqlite").exists()


@pytest.mark.parametrize("text", ["", "{nope", "[]", '{"entries": 5}', "\x00\x01"])
def test_a_missing_or_damaged_file_is_an_empty_list(tmp_path, text):
    folder = make_project(tmp_path, "Other")
    assert clipboard_browse.read_entries(folder) == []  # none written yet
    project_path(folder).write_text(text, encoding="utf-8")
    assert clipboard_browse.read_entries(folder) == []


def test_a_clipboard_that_is_a_link_is_not_followed(tmp_path):
    folder = make_project(tmp_path, "Other")
    outside = tmp_path / "elsewhere.json"
    ClipboardStore(outside).update(lambda h: h.add(entry(1)))
    project_path(folder).symlink_to(outside)
    assert clipboard_browse.read_entries(folder) == []


def test_a_conflicted_copy_is_not_read(tmp_path):
    folder = make_project(tmp_path, "Other", entry(1))
    (folder / "clipboard (conflicted copy).json").write_text(
        project_path(folder).read_text().replace("name 1", "theirs"))
    assert [e.name for e in clipboard_browse.read_entries(folder)] == ["name 1"]


# -- the recent projects -------------------------------------------------------


@pytest.fixture
def recents(tmp_path, monkeypatch):
    file = tmp_path / "recents.json"
    monkeypatch.setattr(desktop, "recents_file", lambda: file)
    return file


def test_headless_there_are_no_recents(session, recents):
    assert session.clipboard_projects() == []


def test_the_recent_projects_list_name_path_time_and_count(tmp_path, session, recents):
    one = make_project(tmp_path, "One", entry(1), entry(2))
    two = make_project(tmp_path, "Two")
    gone = tmp_path / "Gone.kuulas"
    desktop.add_recent(recents, str(two))
    desktop.add_recent(recents, str(session.package.path))  # this one is not "other"
    desktop.add_recent(recents, str(one))
    recents.write_text(json.dumps([*json.loads(recents.read_text()), str(gone)]))
    listed = session.clipboard_projects()
    assert [p["name"] for p in listed] == ["One", "Two"]  # most recent first
    assert [p["path"] for p in listed] == [str(one.resolve()), str(two.resolve())]
    assert [p["entries"] for p in listed] == [2, 0]
    assert all(isinstance(p["last_opened"], str) for p in listed)


def test_a_project_with_a_broken_clipboard_still_lists(tmp_path, session, recents):
    one = make_project(tmp_path, "One")
    project_path(one).write_text("{nope", encoding="utf-8")
    desktop.add_recent(recents, str(one))
    assert session.clipboard_projects()[0]["entries"] == 0


def test_last_opened_is_the_resume_time_when_there_is_one(tmp_path, session, recents):
    one = make_project(tmp_path, "One")
    (one / "resume.json").write_text(json.dumps({"saved_at": "2026-10-18T19:00:00Z"}))
    desktop.add_recent(recents, str(one))
    assert session.clipboard_projects()[0]["last_opened"] == "2026-10-18T19:00:00Z"


# -- adopting ------------------------------------------------------------------


def test_adopting_makes_a_new_entry_here_and_leaves_the_original(tmp_path, session):
    other = make_project(tmp_path, "Other", entry(1, source="/x/Other.kuulas",
                                                  name="Intro", shared=True))
    (found,) = clipboard_browse.read_entries(other)
    adopted = session.clipboard_adopt(
        {**session._entry_view(found, session.state), "length": 99, "clips": 7})
    assert adopted["id"] != "e0001"
    assert adopted["name"] == "Intro"
    assert adopted["adopted_from"] == "/x/Other.kuulas"
    assert adopted["shared"] is False  # the copy here is this project's own
    (mine,) = session.clipboard.load().entries()
    assert mine.id == adopted["id"]
    assert mine.refs == found.refs
    assert mine.source_project == "/x/Other.kuulas"  # where its media can be found
    stored = json.loads(project_path(session.package.path).read_text())["entries"][0]
    assert "length" not in stored  # view fields are not data
    assert "clips" not in stored
    assert [e.id for e in clipboard_browse.read_entries(other)] == ["e0001"]


def test_adopting_from_a_project_without_a_recorded_source_names_that_project(
        tmp_path, session):
    other = make_project(tmp_path, "Other", entry(1))
    (found,) = clipboard_browse.read_entries(other)
    adopted = session.clipboard_adopt(session._entry_view(found, session.state),
                                      from_project=str(other))
    assert adopted["adopted_from"] == str(other)


@pytest.mark.parametrize("bad", [None, [], "x", {}, {"id": "x"}, {"id": "x", "refs": 5},
                                 {"id": "x", "refs": [{"offset": 1}]}])
def test_adopting_something_that_is_not_an_entry_is_an_error(session, bad):
    with pytest.raises(EditError):
        session.clipboard_adopt(bad)
    assert session.clipboard.load().entries() == ()


def test_an_adopted_entry_pastes_like_any_other(tmp_path, session):
    source = Session(tmp_path / "Source.kuulas")
    try:
        source.import_media([str(wav(tmp_path / "b.wav", 7))])
        clip = source.state.tracks[0].clips[0].id
        made = source.clipboard_copy(clip_ids=[clip])["entry"]
        adopted = session.clipboard_adopt(made)
        result = session.clipboard_paste(adopted["id"], at=0, mode="overwrite",
                                         target_tracks={0: session.state.tracks[0].id})
        assert result["placed"] == 1  # the recording was linked from where it lives
    finally:
        source.close()


# -- the API -------------------------------------------------------------------


class _Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


@pytest.fixture
def client(session, tmp_path, recents):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _Engine(), language="en", ui_dir=ui)) as c:
        yield c


def test_api_projects_and_one_projects_entries(tmp_path, client, recents):
    one = make_project(tmp_path, "One", entry(1, name="Hello"))
    desktop.add_recent(recents, str(one))
    listed = client.get("/api/clipboard/projects").json()["projects"]
    assert [(p["name"], p["entries"]) for p in listed] == [("One", 1)]
    got = client.get("/api/clipboard/project", params={"path": str(one)}).json()
    assert got["project"]["name"] == "One"
    assert [e["name"] for e in got["entries"]] == ["Hello"]
    assert got["entries"][0]["length"] == 100


def test_api_a_damaged_clipboard_is_an_empty_list_not_an_error(tmp_path, client):
    one = make_project(tmp_path, "One")
    project_path(one).write_text("{nope")
    r = client.get("/api/clipboard/project", params={"path": str(one)})
    assert r.status_code == 200
    assert r.json()["entries"] == []


@pytest.mark.parametrize("bad", ["", "relative.kuulas", "/etc", "/etc/passwd",
                                 "/usr/../etc/x.kuulas"])
def test_api_a_bad_path_is_a_400_with_a_key(client, bad):
    r = client.get("/api/clipboard/project", params={"path": bad})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.clipboard.bad_project"


def test_api_adopt_then_list(tmp_path, client, session):
    one = make_project(tmp_path, "One", entry(1, name="Hello"))
    got = client.get("/api/clipboard/project", params={"path": str(one)}).json()
    r = client.post("/api/clipboard/adopt", json={"entry": got["entries"][0],
                                                  "from_project": str(one)})
    assert r.status_code == 200
    body = r.json()
    assert body["entry"]["name"] == "Hello"
    assert [e["id"] for e in body["entries"]] == [body["entry"]["id"]]
    assert body["entries"][0]["adopted_from"] == str(one)


def test_api_adopt_of_garbage_is_a_400(client):
    r = client.post("/api/clipboard/adopt", json={"entry": {"refs": 5}})
    assert r.status_code == 400
    assert client.post("/api/clipboard/adopt", json={}).status_code == 400


def test_the_server_never_writes_into_the_folder_it_browses(tmp_path, client):
    one = make_project(tmp_path, "One", entry(1))
    before = sorted((p.name, p.stat().st_mtime_ns) for p in one.rglob("*") if p.is_file())
    client.get("/api/clipboard/project", params={"path": str(one)})
    assert sorted((p.name, p.stat().st_mtime_ns)
                  for p in one.rglob("*") if p.is_file()) == before


# -- the desktop bridge --------------------------------------------------------


class _FakeWebview:
    class FileDialog:
        FOLDER = "folder"


class _FakeWindow:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def create_file_dialog(self, kind, **options):
        self.calls.append((kind, options))
        return self.answer


def _bridge(tmp_path, answer):
    bridge = desktop.Bridge(_FakeWebview, tmp_path / "recents")
    bridge._window = _FakeWindow(answer)
    return bridge


def test_the_bridge_picks_a_project_folder(tmp_path):
    bridge = _bridge(tmp_path, [str(tmp_path / "Other.kuulas")])
    assert bridge.pick_project_folder() == str(tmp_path / "Other.kuulas")
    [(kind, _options)] = bridge._window.calls
    assert kind == "folder"


def test_the_bridge_answers_none_on_cancel(tmp_path):
    assert _bridge(tmp_path, None).pick_project_folder() is None
    assert _bridge(tmp_path, []).pick_project_folder() is None


def test_the_recents_file_can_be_set_by_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_RECENTS_FILE", str(tmp_path / "r.json"))
    assert desktop.recents_file() == tmp_path / "r.json"
    monkeypatch.delenv("KUULAS_RECENTS_FILE")
    assert desktop.recents_file() == desktop.config_dir() / "recent.json"
