"""File > New project... and Open project... in the desktop window (WP74): the native
dialog names the folder and the project opens in a window of its own (never replaces
the one the owner is working in)."""

from __future__ import annotations

from kuulas import desktop


class _Webview:
    class FileDialog:
        FOLDER = "folder"
        SAVE = "save"


class _Window:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.evaluated = []

    def create_file_dialog(self, kind, **options):
        self.calls.append((kind, options))
        return self.answer

    def evaluate_js(self, script):
        self.evaluated.append(script)


def _bridge(tmp_path, answer):
    opened = []
    bridge = desktop.Bridge(_Webview, tmp_path / "recents")
    bridge._window = _Window(answer)
    bridge._opener = opened.append
    return bridge, opened


def test_new_project_asks_for_a_name_and_opens_it_in_a_window(tmp_path):
    bridge, opened = _bridge(tmp_path, [str(tmp_path / "Fresh")])
    assert bridge.new_project_in_window() is True
    [(kind, options)] = bridge._window.calls
    assert kind == "save"
    assert options["save_filename"] == "Untitled.kuulas"
    assert opened == [str(tmp_path / "Fresh.kuulas")]


def test_new_project_keeps_a_suffix_the_dialog_already_has(tmp_path):
    bridge, opened = _bridge(tmp_path, [str(tmp_path / "Fresh.kuulas")])
    assert bridge.new_project_in_window() is True
    assert opened == [str(tmp_path / "Fresh.kuulas")]


def test_cancelling_the_new_project_dialog_does_nothing(tmp_path):
    for answer in (None, []):
        bridge, opened = _bridge(tmp_path, answer)
        assert bridge.new_project_in_window() is False
        assert opened == []


def test_a_name_that_cannot_be_a_folder_is_reported_in_the_window(tmp_path):
    bridge, opened = _bridge(tmp_path, [str(tmp_path / ".kuulas")])
    assert bridge.new_project_in_window() is False
    assert opened == []
    assert len(bridge._window.evaluated) == 1  # the message, shown by the page


def test_open_project_picks_a_folder_and_opens_it_in_a_window(tmp_path):
    bridge, opened = _bridge(tmp_path, [str(tmp_path / "Other.kuulas")])
    assert bridge.open_project_in_window() is True
    [(kind, _options)] = bridge._window.calls
    assert kind == "folder"
    assert opened == [str(tmp_path / "Other.kuulas")]


def test_cancelling_the_open_dialog_does_nothing(tmp_path):
    bridge, opened = _bridge(tmp_path, None)
    assert bridge.open_project_in_window() is False
    assert opened == []


def test_without_a_window_app_the_project_opens_in_this_window(tmp_path, monkeypatch):
    bridge = desktop.Bridge(_Webview, tmp_path / "recents")
    bridge._window = _Window([str(tmp_path / "Other.kuulas")])
    seen = []
    monkeypatch.setattr(bridge, "open_project",
                        lambda folder: seen.append(folder) or True)
    assert bridge.open_project_in_window() is True
    assert seen == [str(tmp_path / "Other.kuulas")]
