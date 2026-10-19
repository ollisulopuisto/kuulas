"""The standard Mac commands in the desktop window: Close project (Cmd+W), Open Recent,
Clear menu and Minimise. Ground rule 17: closing never walks away from a take."""

from __future__ import annotations

import json
from pathlib import Path

from kuulas import desktop


class _Webview:
    class FileDialog:
        FOLDER = "folder"
        SAVE = "save"


class _Window:
    def __init__(self):
        self.titles = []
        self.pages = []
        self.minimised = 0

    def set_title(self, title):
        self.titles.append(title)

    def load_html(self, html):
        self.pages.append(html)

    def minimize(self):
        self.minimised += 1

    def evaluate_js(self, script):
        pass


class _Project:
    folder = "/p/Show.kuulas"

    def __init__(self, busy=None):
        self.busy = busy
        self.stopped = 0

    def record_busy(self):
        return self.busy

    def stop(self):
        self.stopped += 1


def _bridge(tmp_path):
    bridge = desktop.Bridge(_Webview, tmp_path / "recents.json")
    bridge._window = _Window()
    return bridge


# -- Close project ---------------------------------------------------------


def test_close_project_stops_the_project_and_shows_the_start_page(tmp_path):
    bridge = _bridge(tmp_path)
    project = _Project()
    bridge._project = project
    assert bridge.close_project() == {"closed": True}
    assert project.stopped == 1
    assert bridge.project_folder is None
    assert len(bridge._window.pages) == 1


def test_close_project_refuses_while_a_take_records(tmp_path):
    bridge = _bridge(tmp_path)
    project = _Project(busy="recording")
    bridge._project = project
    assert bridge.close_project() == {"closed": False, "reason": "recording"}
    assert project.stopped == 0
    assert bridge.project_folder == "/p/Show.kuulas"
    assert bridge._window.pages == []


def test_close_project_refuses_while_the_microphone_is_armed(tmp_path):
    bridge = _bridge(tmp_path)
    bridge._project = _Project(busy="armed")
    assert bridge.close_project() == {"closed": False, "reason": "armed"}


def test_close_project_on_the_start_page_is_harmless(tmp_path):
    bridge = _bridge(tmp_path)
    assert bridge.close_project() == {"closed": True}


class _Recorder:
    def __init__(self, view, heard=False):
        self.view = view
        self.heard = heard

    def status(self):
        return self.view

    def recording_now(self):
        return self.heard


def _running(view, heard=False):
    running = object.__new__(desktop.RunningProject)
    running._recorder = _Recorder(view, heard)
    return running


def test_record_busy_names_a_take_of_this_project():
    assert _running({"recording": True, "ours": True}).record_busy() == "recording"


def test_record_busy_names_an_armed_microphone():
    assert _running({"armed": True}).record_busy() == "armed"


def test_a_take_of_another_project_does_not_hold_this_one():
    assert _running({"recording": True, "ours": False}).record_busy() is None


def test_an_idle_recorder_does_not_hold_the_project():
    assert _running({"recording": False, "armed": False}).record_busy() is None


def test_a_recorder_that_cannot_be_asked_but_was_recording_holds_the_project():
    view = {"available": False, "recording": False}
    assert _running(view, heard=True).record_busy() == "recording"
    assert _running(view, heard=False).record_busy() is None


# -- Open Recent -----------------------------------------------------------


def test_open_recent_opens_a_project_that_is_there_in_a_window_of_its_own(tmp_path):
    folder = tmp_path / "Show.kuulas"
    folder.mkdir()
    bridge = _bridge(tmp_path)
    opened = []
    bridge._opener = opened.append
    assert bridge.open_recent_in_window(str(folder)) is True
    assert opened == [str(folder)]


def test_open_recent_of_a_missing_folder_does_nothing(tmp_path):
    bridge = _bridge(tmp_path)
    opened = []
    bridge._opener = opened.append
    assert bridge.open_recent_in_window(str(tmp_path / "gone.kuulas")) is False
    assert opened == []


def test_clear_recent_empties_the_list_and_leaves_the_projects(tmp_path):
    file = tmp_path / "recents.json"
    folder = tmp_path / "Show.kuulas"
    folder.mkdir()
    desktop.add_recent(file, str(folder))
    assert desktop.load_recent_records(file)
    bridge = _bridge(tmp_path)
    assert bridge.clear_recent() is True
    assert desktop.load_recent_records(file) == []
    assert json.loads(file.read_text(encoding="utf-8")) == []
    assert folder.is_dir()


def test_clear_recent_without_a_file_is_fine(tmp_path):
    assert _bridge(tmp_path).clear_recent() is True
    assert json.loads(Path(tmp_path / "recents.json").read_text(encoding="utf-8")) == []


# -- Minimise --------------------------------------------------------------


def test_minimise_asks_the_window(tmp_path):
    bridge = _bridge(tmp_path)
    bridge.minimise()
    assert bridge._window.minimised == 1
