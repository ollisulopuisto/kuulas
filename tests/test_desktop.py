"""The desktop wrapper's pure parts (WP15): no window, no GUI toolkit."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from kuulas import cli, desktop, messages
from kuulas.resume import read_resume


def test_config_dir_per_platform(tmp_path):
    home = tmp_path / "home"
    mac = desktop.config_dir("darwin", {}, home)
    assert mac == home / "Library/Application Support/kuulas"
    assert desktop.config_dir("win32", {"APPDATA": str(tmp_path / "ad")}, home) == (
        tmp_path / "ad" / "kuulas")
    assert desktop.config_dir("linux", {}, home) == home / ".config" / "kuulas"


def test_config_dir_windows_without_appdata_falls_back_under_home(tmp_path):
    got = desktop.config_dir("win32", {}, tmp_path)
    assert got == tmp_path / "AppData/Roaming/kuulas"


def test_config_dir_linux_honours_xdg(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path / "x")}
    assert desktop.config_dir("linux", env, tmp_path) == tmp_path / "x" / "kuulas"


def folders(tmp_path, n):
    out = []
    for i in range(n):
        folder = tmp_path / f"P{i}.kuulas"
        folder.mkdir()
        out.append(str(folder))
    return out


def test_recents_most_recent_first_and_deduplicated(tmp_path):
    file = tmp_path / "recent.json"
    a, b = folders(tmp_path, 2)
    desktop.add_recent(file, a)
    desktop.add_recent(file, b)
    desktop.add_recent(file, a)
    assert desktop.load_recents(file) == [a, b]


def test_recents_capped_at_twenty(tmp_path):
    file = tmp_path / "recent.json"
    paths = folders(tmp_path, 25)
    for p in paths:
        desktop.add_recent(file, p)
    got = desktop.load_recents(file)
    assert len(got) == 20
    assert got[0] == paths[-1]
    assert got[-1] == paths[5]


def test_recents_drop_missing_folders_on_read(tmp_path):
    file = tmp_path / "recent.json"
    a, b = folders(tmp_path, 2)
    desktop.add_recent(file, a)
    desktop.add_recent(file, b)
    Path(a).rmdir()
    assert desktop.load_recents(file) == [b]


@pytest.mark.parametrize("content", ["", "not json", '{"a": 1}', '[1, null, "x"]'])
def test_recents_survive_a_damaged_file(tmp_path, content):
    file = tmp_path / "recent.json"
    file.write_text(content, encoding="utf-8")
    assert desktop.load_recents(file) == []
    (a,) = folders(tmp_path, 1)
    desktop.add_recent(file, a)
    assert desktop.load_recents(file) == [a]


def test_recents_file_is_written_atomically_and_creates_its_folder(tmp_path):
    file = tmp_path / "deep" / "er" / "recent.json"
    (a,) = folders(tmp_path, 1)
    desktop.add_recent(file, a)
    assert json.loads(file.read_text(encoding="utf-8")) == [a]
    assert not list(file.parent.glob("*.tmp"))


def test_window_title_uses_the_project_name():
    def title(key, **kw):
        return messages.t(key, **kw)

    got = desktop.window_title("/x/Interview.kuulas")
    assert got == title("desktop.title", name="Interview")
    got = desktop.window_title("C:\\x\\Show 3.kuulas")
    assert got == title("desktop.title", name="Show 3")
    assert desktop.window_title(None) == "kuulas"


def test_menu_model_has_the_planned_menus_and_unique_ids():
    menus = desktop.menu_model()
    assert [m["id"] for m in menus] == ["file", "edit", "view", "window", "help"]
    ids = [i["id"] for m in menus for i in m["items"] if i is not None]
    assert len(ids) == len(set(ids))
    wanted = {"file.open", "file.import", "file.export", "edit.undo", "edit.redo",
              "view.zoom_in", "view.zoom_out", "view.density", "help.search"}
    assert wanted <= set(ids)


@pytest.mark.parametrize("lang", ["en", "fi"])
def test_menu_labels_exist_in_both_catalogs(lang):
    catalog = messages._CATALOGS[lang]
    for menu in desktop.menu_model():
        assert menu["label"] in catalog
        for item in menu["items"]:
            if item is not None:
                assert item["label"] in catalog


def test_localised_menu_resolves_labels(monkeypatch):
    messages.set_language("fi")
    try:
        menus = desktop.localised_menu()
        assert menus[0]["label"] == messages.t("desktop.menu.file")
        assert menus[0]["label"] != "desktop.menu.file"
    finally:
        messages.set_language("en")


def test_running_project_serves_and_stops(tmp_path):
    first = desktop.RunningProject(str(tmp_path / "A.kuulas"))
    second = desktop.RunningProject(str(tmp_path / "B.kuulas"))
    try:
        assert first.url != second.url
        assert first.url.startswith("http://127.0.0.1:")
        assert httpx.get(first.url + "api/state", timeout=10).status_code == 200
        assert httpx.get(first.url, timeout=10).status_code == 200
    finally:
        first.stop()
        second.stop()
    with pytest.raises(httpx.TransportError):
        httpx.get(first.url + "api/state", timeout=2)


def test_closing_the_window_saves_where_the_engine_was(tmp_path):
    """Closing while playing sends no more page events: the server knows the position."""
    folder = tmp_path / "A.kuulas"
    running = desktop.RunningProject(str(folder))
    try:
        body = {"view": {"playhead": 5, "zoom": 2}}
        sent = httpx.put(running.url + "api/view-memory", json=body, timeout=10)
        assert sent.status_code == 200
        running._engine.status = lambda: {"position": 123456}
    finally:
        running.stop()
    assert read_resume(folder)["playhead"] == 123456


def test_missing_extra_gives_a_translated_message(monkeypatch, capsys):
    monkeypatch.setattr(desktop, "load_webview", lambda: None)
    assert desktop.run_launcher() == 1
    err = capsys.readouterr().err
    assert "kuulas[desktop]" in err
    assert err.strip() == messages.t("desktop.missing_extra")


def test_no_arguments_opens_the_launcher(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop, "run_launcher", lambda: calls.append("launcher") or 0)
    monkeypatch.setattr(desktop, "run_window", lambda f: calls.append(f) or 0)
    assert cli.main([]) == 0
    assert cli.main(["open", "X.kuulas", "--window"]) == 0
    assert calls == ["launcher", "X.kuulas"]


def test_launcher_page_escapes_and_lists_recents():
    page = desktop.launcher_html(['/x/<b>Show</b>.kuulas'])
    assert "<b>Show" not in page
    assert "&lt;b&gt;Show" in page


def test_launcher_page_shows_the_mark():
    page = desktop.launcher_html([])
    assert "data:image/svg+xml;base64," in page
    assert 'class="mark"' in page


def test_icon_paths_exist_in_the_package():
    assert desktop.icon_path("dock").is_file()
    assert desktop.icon_path("window").is_file()


def test_dock_icon_is_set_only_on_macos_and_never_raises(tmp_path):
    calls = []

    class FakeApp:
        @staticmethod
        def sharedApplication():  # noqa: N802
            return FakeApp()

        def setApplicationIconImage_(self, image):  # noqa: N802
            calls.append(image)

    class FakeImage:
        @staticmethod
        def alloc():
            return FakeImage()

        def initWithContentsOfFile_(self, path):  # noqa: N802
            return ("image", path)

    appkit = type("AppKit", (), {"NSApplication": FakeApp, "NSImage": FakeImage})
    assert desktop.set_dock_icon(platform="linux", appkit=appkit) is False
    assert calls == []
    assert desktop.set_dock_icon(platform="darwin", appkit=appkit) is True
    assert calls[0][0] == "image"
    assert desktop.set_dock_icon(platform="darwin", appkit=None) is False
