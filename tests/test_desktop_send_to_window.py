"""Edit > Clipboard > Copy to other window (owner, 2026-10-23): an entry copied in one
project window goes onto the clipboard of another open project, in this process, so
two windows on two episodes trade material in two actions."""

from __future__ import annotations

import json
from types import SimpleNamespace

from kuulas import desktop


class _Webview:
    class FileDialog:
        FOLDER = "folder"


class _Window:
    def __init__(self):
        self.evaluated = []

    def evaluate_js(self, script):
        self.evaluated.append(script)


class _Session:
    def __init__(self):
        self.adopted = []

    def clipboard_adopt(self, entry, from_project=""):
        self.adopted.append((entry, from_project))
        return {"id": "new-id", "name": entry.get("name", "")}


def _app(tmp_path, *folders):
    app = desktop.WindowApp(_Webview, tmp_path / "recents")
    for folder in folders:
        bridge = desktop.Bridge(_Webview, tmp_path / "recents")
        bridge._window = _Window()
        bridge._app = app
        if folder is not None:
            bridge._project = SimpleNamespace(folder=folder, session=_Session())
        app._bridges.append(bridge)
    return app


def test_the_other_windows_with_a_project_are_listed_by_name(tmp_path):
    app = _app(tmp_path, "/p/Episode 1.kuulas", "/p/Episode 2.kuulas", None)
    first, second, launcher = app._bridges
    two = {"folder": "/p/Episode 2.kuulas", "name": "Episode 2"}
    one = {"folder": "/p/Episode 1.kuulas", "name": "Episode 1"}
    assert first.other_windows() == [two]
    assert second.other_windows() == [one]
    # A window still on the launcher page has no clipboard to receive.
    assert launcher.other_windows() == [one, two]


def test_a_lone_window_has_no_other_windows(tmp_path):
    app = _app(tmp_path, "/p/Episode 1.kuulas")
    assert app._bridges[0].other_windows() == []


def test_sending_adopts_the_entry_into_the_other_project_only(tmp_path):
    app = _app(tmp_path, "/p/Episode 1.kuulas", "/p/Episode 2.kuulas")
    one, two = app._bridges
    entry = {"id": "e1", "name": "Intro joke"}
    answer = one.send_to_window("/p/Episode 2.kuulas", entry)
    assert answer == {"ok": True, "name": "Episode 2"}
    assert two._project.session.adopted == [(entry, "/p/Episode 1.kuulas")]
    assert one._project.session.adopted == []


def test_the_receiving_window_is_told_what_arrived_and_from_where(tmp_path):
    app = _app(tmp_path, "/p/Episode 1.kuulas", "/p/Episode 2.kuulas")
    one, two = app._bridges
    one.send_to_window("/p/Episode 2.kuulas", {"id": "e1", "name": "Intro joke"})
    [script] = two._window.evaluated
    prefix = "window.kuulasClipboardArrived&&window.kuulasClipboardArrived("
    assert script.startswith(prefix)
    payload = json.loads(script[len(prefix):-1])
    assert payload == {"from": "Episode 1",
                       "entry": {"id": "new-id", "name": "Intro joke"}}
    assert one._window.evaluated == []


def test_a_window_that_was_closed_meanwhile_is_not_an_error(tmp_path):
    app = _app(tmp_path, "/p/Episode 1.kuulas", "/p/Episode 2.kuulas")
    one = app._bridges[0]
    assert one.send_to_window("/p/Nowhere.kuulas", {"id": "e1"}) == {
        "ok": False, "reason": "gone"}


def test_a_window_cannot_send_to_itself(tmp_path):
    app = _app(tmp_path, "/p/Episode 1.kuulas", "/p/Episode 2.kuulas")
    one = app._bridges[0]
    assert one.send_to_window("/p/Episode 1.kuulas", {"id": "e1"}) == {
        "ok": False, "reason": "gone"}
    assert one._project.session.adopted == []


def test_a_bridge_without_an_app_sees_no_other_windows(tmp_path):
    bridge = desktop.Bridge(_Webview, tmp_path / "recents")
    assert bridge.other_windows() == []
    assert bridge.send_to_window("/p/x.kuulas", {}) == {"ok": False, "reason": "gone"}
