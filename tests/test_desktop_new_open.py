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


def test_a_save_dialog_that_answers_with_one_string_is_one_path(tmp_path):
    # pywebview on macOS answers a SAVE dialog with a plain str, not a tuple; read as a
    # list of paths it gave "/" (its first character) and "name cannot be empty".
    bridge, opened = _bridge(tmp_path, str(tmp_path / "synctest2"))
    assert bridge.new_project_in_window() is True
    assert opened == [str(tmp_path / "synctest2.kuulas")]
    assert bridge.pick_save("x.wav") == str(tmp_path / "synctest2")


def test_a_new_episode_opens_in_a_window_of_its_own(tmp_path):
    # Series > New episode from series… makes the project on the server; the page then
    # asks the window to open that folder (docs/design/SERIES.md).
    episode = tmp_path / "Ep 2.kuulas"
    episode.mkdir()
    (episode / "manifest.json").write_text("{}")
    bridge, opened = _bridge(tmp_path, None)
    assert bridge.open_path_in_window(str(episode)) is True
    assert opened == [str(episode)]


def test_open_path_refuses_what_is_not_a_project(tmp_path):
    bridge, opened = _bridge(tmp_path, None)
    missing = str(tmp_path / "missing.kuulas")
    for bad in ("", "relative.kuulas", missing, 5, str(tmp_path)):
        assert bridge.open_path_in_window(bad) is False
    assert opened == []
