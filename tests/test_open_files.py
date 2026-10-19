"""Open-files events (WP73): a double-clicked ``.kuulas`` folder opens in a window.

No window and no Cocoa: a fake web view records what the app asked of it.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import ClassVar

from kuulas import desktop
from kuulas.openfiles import project_paths


def project(tmp_path: Path, name: str = "A.kuulas") -> str:
    folder = tmp_path / name
    folder.mkdir()
    return str(folder)


# -- which paths are projects ----------------------------------------


def test_a_kuulas_folder_is_a_project(tmp_path):
    folder = project(tmp_path)
    assert project_paths([folder]) == [str(Path(folder).resolve())]


def test_a_folder_with_a_manifest_is_a_project_whatever_its_name(tmp_path):
    folder = tmp_path / "renamed"
    folder.mkdir()
    (folder / "manifest.json").write_text("{}", encoding="utf-8")
    assert project_paths([str(folder)]) == [str(folder.resolve())]


def test_files_other_folders_and_missing_paths_are_not_projects(tmp_path):
    plain = tmp_path / "docs"
    plain.mkdir()
    file = tmp_path / "x.kuulas"
    file.write_text("a file, not a package", encoding="utf-8")
    assert project_paths([str(plain), str(file), str(tmp_path / "gone.kuulas")]) == []


def test_duplicates_collapse_and_order_is_kept(tmp_path):
    a, b = project(tmp_path, "A.kuulas"), project(tmp_path, "B.kuulas")
    got = project_paths([a, b, a])
    assert got == [str(Path(a).resolve()), str(Path(b).resolve())]


# -- the app that receives them --------------------------------------


class FakeWindow:
    def __init__(self, title, html=None, js_api=None, **options):
        self.title, self.html, self.js_api, self.options = title, html, js_api, options
        self.urls: list[str] = []
        self.shown = 0
        self.events = type("E", (), {})()
        for name in ("loaded", "closed"):
            setattr(self.events, name, _Event())
        self.dom = type("D", (), {"document": type("Doc", (), {
            "events": type("Ev", (), {"drop": _Event()})()})()})()

    def set_title(self, title):
        self.title = title

    def load_url(self, url):
        self.urls.append(url)

    def load_html(self, html):
        self.html = html

    def show(self):
        self.shown += 1

    def restore(self):
        self.shown += 1


class _Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWebview:
    def __init__(self):
        self.windows: list[FakeWindow] = []

    def create_window(self, title, **kwargs):
        window = FakeWindow(title, **kwargs)
        self.windows.append(window)
        return window


class FakeRunning:
    stopped: ClassVar[list[str]] = []

    def __init__(self, folder):
        self.folder = folder
        self.url = f"http://127.0.0.1/{Path(folder).name}"

    def stop(self):
        FakeRunning.stopped.append(self.folder)


def make_app(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "RunningProject", FakeRunning)
    FakeRunning.stopped = []
    webview = FakeWebview()
    app = desktop.WindowApp(webview, tmp_path / "recent.json", lambda _bridge: None)
    first = app.new_window()
    return app, webview, first


def test_an_event_before_the_app_is_ready_waits_and_opens_in_the_first_window(
        tmp_path, monkeypatch):
    app, webview, first = make_app(tmp_path, monkeypatch)
    folder = project(tmp_path)
    app.open_paths([folder])
    assert webview.windows[0].urls == []  # the window is not up yet
    app.ready()
    assert webview.windows[0].urls == [f"http://127.0.0.1/{Path(folder).name}"]
    assert len(webview.windows) == 1
    assert webview.windows[0].title == desktop.window_title(str(Path(folder).resolve()))
    assert first.recent() == [str(Path(folder).resolve())]


def test_a_second_project_opens_in_a_second_window(tmp_path, monkeypatch):
    app, webview, _first = make_app(tmp_path, monkeypatch)
    app.ready()
    a, b = project(tmp_path, "A.kuulas"), project(tmp_path, "B.kuulas")
    app.open_paths([a])
    app.open_paths([b])
    assert len(webview.windows) == 2
    assert webview.windows[0].urls == ["http://127.0.0.1/A.kuulas"]
    assert webview.windows[1].urls == ["http://127.0.0.1/B.kuulas"]


def test_a_project_that_is_already_open_is_brought_forward_not_opened_twice(
        tmp_path, monkeypatch):
    app, webview, _first = make_app(tmp_path, monkeypatch)
    app.ready()
    folder = project(tmp_path)
    app.open_paths([folder])
    app.open_paths([folder])
    assert len(webview.windows) == 1
    assert webview.windows[0].urls == ["http://127.0.0.1/A.kuulas"]
    assert webview.windows[0].shown >= 1


def test_several_projects_in_one_event_open_one_window_each(tmp_path, monkeypatch):
    app, webview, _first = make_app(tmp_path, monkeypatch)
    app.ready()
    app.open_paths([project(tmp_path, "A.kuulas"), project(tmp_path, "B.kuulas")])
    assert [w.urls for w in webview.windows] == [
        ["http://127.0.0.1/A.kuulas"], ["http://127.0.0.1/B.kuulas"]]


def test_something_that_is_not_a_project_opens_nothing(tmp_path, monkeypatch):
    app, webview, _first = make_app(tmp_path, monkeypatch)
    app.ready()
    app.open_paths([str(tmp_path)])
    assert len(webview.windows) == 1
    assert webview.windows[0].urls == []


def test_closing_a_window_stops_its_project_and_frees_it_to_be_opened_again(
        tmp_path, monkeypatch):
    app, webview, _first = make_app(tmp_path, monkeypatch)
    app.ready()
    folder = project(tmp_path)
    app.open_paths([folder])
    for handler in webview.windows[0].events.closed.handlers:
        handler()
    assert FakeRunning.stopped == [str(Path(folder).resolve())]
    app.open_paths([folder])
    assert len(webview.windows) == 2  # not "already open" any more


# -- the Cocoa hook ---------------------------------------------------


def test_the_open_files_method_hands_paths_to_the_callback_and_replies():
    got: list[list[str]] = []
    done = threading.Event()

    def callback(paths):
        got.append(paths)
        done.set()

    method = desktop.make_open_files_method(callback)

    class Cocoa:
        replies: ClassVar[list[int]] = []

        def replyToOpenOrPrint_(self, code):  # noqa: N802 - Cocoa's name
            self.replies.append(code)

    cocoa = Cocoa()
    method(None, cocoa, ["/x/A.kuulas", "/x/B.kuulas"])
    assert done.wait(2)
    assert got == [["/x/A.kuulas", "/x/B.kuulas"]]
    assert cocoa.replies == [0]  # NSApplicationDelegateReplySuccess


def test_installing_the_hook_adds_application_openfiles_to_the_delegate_class():
    added = []

    class FakeObjc:
        @staticmethod
        def selector(func, selector, signature):
            return ("selector", selector, signature)

        @staticmethod
        def classAddMethod(klass, name, method):  # noqa: N802 - PyObjC's name
            added.append((klass, name, method))

    delegate = type("Delegate", (), {})
    assert desktop.install_open_files_hook(lambda _paths: None, objc=FakeObjc,
                                           delegate_class=delegate)
    assert added == [(delegate, b"application:openFiles:",
                      ("selector", b"application:openFiles:", b"v@:@@"))]


def test_the_hook_is_skipped_off_macos_and_never_raises():
    assert not desktop.install_open_files_hook(lambda _paths: None, platform="linux")
    assert not desktop.install_open_files_hook(
        lambda _paths: None, platform="darwin", objc=None, delegate_class=None)
