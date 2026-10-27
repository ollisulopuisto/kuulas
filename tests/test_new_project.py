"""File > New project... / Open project... (WP74): the pure parts (the name, the folder)
and the two server routes that make or check a project and start a window on it (the
starter is faked)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import messages, new_project
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.mark.parametrize(("typed", "folder"), [
    ("My show", "My show.kuulas"),
    ("  Episode 12  ", "Episode 12.kuulas"),
    ("Show.kuulas", "Show.kuulas"),
    ("Show.KUULAS", "Show.kuulas"),
    ("Äänet ja öljy", "Äänet ja öljy.kuulas"),
    ("v1.2", "v1.2.kuulas"),
])
def test_the_folder_name_gets_the_kuulas_suffix_once(typed, folder):
    assert new_project.folder_name(typed) == folder


@pytest.mark.parametrize("typed", [
    "", "   ", ".kuulas", " .kuulas", "a/b", "a\\b", "a\0b", ".", "..", ".hidden",
    "x" * 101,
])
def test_a_bad_name_is_refused_with_a_message(typed):
    with pytest.raises(EditError) as raised:
        new_project.folder_name(typed)
    assert raised.value.key == "error.project.bad_name"


def test_project_path_joins_parent_and_name(tmp_path):
    assert new_project.project_path(str(tmp_path), "Show") == tmp_path / "Show.kuulas"


def test_project_path_refuses_a_bad_parent_and_an_existing_project(tmp_path):
    with pytest.raises(EditError) as raised:
        new_project.project_path("relative/folder", "Show")
    assert raised.value.key == "error.project.bad_parent"
    with pytest.raises(EditError) as raised:
        new_project.project_path(str(tmp_path / "missing"), "Show")
    assert raised.value.key == "error.project.bad_parent"
    with pytest.raises(EditError) as raised:
        new_project.project_path(str(tmp_path / ".." / tmp_path.name), "Show")
    assert raised.value.key == "error.project.bad_parent"
    (tmp_path / "Show.kuulas").mkdir()
    with pytest.raises(EditError) as raised:
        new_project.project_path(str(tmp_path), "Show")
    assert raised.value.key == "error.project.exists"


def test_project_path_refuses_symlink_to_non_directory(tmp_path):
    link = tmp_path / "link_to_file"
    target = tmp_path / "some_file.txt"
    target.write_text("x")
    link.symlink_to(target)
    with pytest.raises(EditError) as raised:
        new_project.project_path(str(link), "Show")
    assert raised.value.key == "error.project.bad_parent"


def test_spawn_command_opens_the_project_in_a_new_window():
    command = new_project.window_command("/x/Show.kuulas", executable="/py")
    assert command == ["/py", "-m", "kuulas", "open", "/x/Show.kuulas"]


@pytest.fixture
def started(monkeypatch):
    calls = []
    monkeypatch.setattr(new_project, "start_window", calls.append)
    return calls


@pytest.fixture
def client(tmp_path, started):
    ui = tmp_path / "ui"
    ui.mkdir()
    session = Session(tmp_path / "Open.kuulas")
    with TestClient(create_app(session, FakeEngine(), language="en", ui_dir=ui)) as c:
        yield c
    session.close()


def test_new_project_makes_the_folder_and_starts_a_window(client, tmp_path, started):
    r = client.post("/api/project/new", json={"parent": str(tmp_path), "name": "Fresh"})
    assert r.status_code == 200, r.text
    folder = tmp_path / "Fresh.kuulas"
    assert r.json() == {"path": str(folder)}
    assert (folder / "manifest.json").is_file()
    assert started == [str(folder)]


def test_a_bad_name_is_a_400_and_starts_nothing(client, tmp_path, started):
    r = client.post("/api/project/new", json={"parent": str(tmp_path), "name": "a/b"})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.project.bad_name"
    assert started == []


def test_open_project_checks_the_folder_is_a_project(client, tmp_path, started):
    r = client.post("/api/project/open", json={"path": str(tmp_path / "Nope.kuulas")})
    assert r.status_code == 400
    assert started == []
    made = Session(tmp_path / "Other.kuulas")
    made.close()
    r = client.post("/api/project/open", json={"path": str(tmp_path / "Other.kuulas")})
    assert r.status_code == 200, r.text
    assert started == [str((tmp_path / "Other.kuulas").resolve())]


BAD_FOLDERS = [
    "Show.kuulas",
    "-x.kuulas",
    "--port=1.kuulas",
    "a\0.kuulas",
    "",
    "/nope/S.kuulas",
]


def record_spawns(monkeypatch):
    spawned = []
    def popen(*args, **kwargs):
        spawned.append((args, kwargs))

    monkeypatch.setattr(new_project.subprocess, "Popen", popen)
    return spawned


@pytest.mark.parametrize("folder", BAD_FOLDERS)
def test_a_window_is_only_started_for_a_real_project_folder(monkeypatch, folder):
    """The folder comes from the browser request: CodeQL py/command-line-injection (58).
    Only an absolute, existing folder named *.kuulas may start a window."""
    spawned = record_spawns(monkeypatch)
    with pytest.raises(EditError) as raised:
        new_project.start_window(folder)
    assert raised.value.key == "error.project.bad_parent"
    assert spawned == []


def test_a_real_project_folder_opens_in_a_new_window(monkeypatch, tmp_path):
    """CodeQL py/command-line-injection (66): the folder is the child's working
    directory, never an argument, so no request text reaches the command line."""
    project = tmp_path / "Show.kuulas"
    project.mkdir()
    spawned = record_spawns(monkeypatch)
    new_project.start_window(str(project))
    assert len(spawned) == 1
    args, kwargs = spawned[0]
    assert args[0][-2:] == ["open", "."]
    assert kwargs["cwd"] == str(project.resolve())
