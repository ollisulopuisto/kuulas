"""The desktop wrapper (WP15): kuulas in a native window.

The window is a system web view (pywebview) on the same FastAPI app that
``kuulas open`` serves to a browser; nothing of the server is forked. What the
window adds: keys the browser keeps (Cmd+T, Cmd+W, Cmd+N, F6, Cmd+L), native
file dialogs, a native menu and dropped-file *paths*, so media is linked in
place instead of uploaded.

The parts that need no GUI toolkit (config folder, recent projects, title, menu
model, the server thread) are plain functions and classes and are tested alone.
``webview`` is imported only by :func:`load_webview`, so a base install, and
the tests, never need it.
"""

from __future__ import annotations

import html
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

import uvicorn

from .cli import HOST, bind_local, uvicorn_config
from .messages import KuulasError, t

#: Most recent first; older entries fall off.
MAX_RECENT = 20


# -- where per-user state lives -------------------------------------


def config_dir(platform: str | None = None, env: dict[str, str] | None = None,
               home: Path | None = None) -> Path:
    """The per-user kuulas folder, found without a dependency (platformdirs)."""
    platform = sys.platform if platform is None else platform
    env = dict(os.environ) if env is None else env
    home = Path.home() if home is None else home
    if platform == "darwin":
        return home / "Library" / "Application Support" / "kuulas"
    if platform.startswith("win"):
        base = env.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / "kuulas"
    base = env.get("XDG_CONFIG_HOME")
    return (Path(base) if base else home / ".config") / "kuulas"


def recents_file() -> Path:
    return config_dir() / "recent.json"


def load_recents(file: Path) -> list[str]:
    """The recent project folders that still exist, most recent first. A missing
    or damaged file is an empty list: the list is a convenience, never an error."""
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    seen: list[str] = []
    for item in data:
        if isinstance(item, str) and item not in seen and Path(item).is_dir():
            seen.append(item)
    return seen[:MAX_RECENT]


def add_recent(file: Path, folder: str) -> None:
    """Put ``folder`` first. Written through a temp file and renamed, so a crash
    leaves the old list rather than half of a new one. A failure to write is
    swallowed: not remembering a project must not stop opening it."""
    folder = str(Path(folder).resolve())
    current = [p for p in load_recents(file) if p != folder]
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        partial = file.with_name(file.name + ".tmp")
        partial.write_text(json.dumps([folder, *current][:MAX_RECENT], indent=1),
                           encoding="utf-8")
        partial.replace(file)
    except OSError:
        return


# -- window title and menu ------------------------------------------


def window_title(folder: str | None) -> str:
    if not folder:
        return "kuulas"
    # Both separators: a Windows path is handled the same on any machine.
    name = folder.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    name = name.removesuffix(".kuulas")
    return t("desktop.title", name=name)


def _item(item_id: str) -> dict[str, str]:
    return {"id": item_id, "label": f"desktop.menu.{item_id}"}


def menu_model() -> list[dict[str, Any]]:
    """The native menu as data: ``label`` is a message key, ``None`` a separator.
    The ids are what the window sends back to :meth:`Bridge.menu`."""
    return [
        {"id": "file", "label": "desktop.menu.file", "items": [
            _item("file.open"), _item("file.import"), None, _item("file.export")]},
        {"id": "edit", "label": "desktop.menu.edit", "items": [
            _item("edit.undo"), _item("edit.redo")]},
        {"id": "view", "label": "desktop.menu.view", "items": [
            _item("view.zoom_in"), _item("view.zoom_out"), None, _item("view.density")]},
        {"id": "window", "label": "desktop.menu.window", "items": [
            _item("window.minimize")]},
    ]


def localised_menu() -> list[dict[str, Any]]:
    return [{**m, "label": t(m["label"]),
             "items": [None if i is None else {**i, "label": t(i["label"])}
                       for i in m["items"]]}
            for m in menu_model()]


# -- the server behind a window -------------------------------------


class RunningProject:
    """A project served on a free localhost port in a background thread: the
    same Session, Engine and app as ``kuulas open``. ``stop`` shuts it down and
    closes the project, so closing the window leaves nothing running."""

    def __init__(self, folder: str) -> None:
        # Imported here: the engine pulls in the audio libraries.
        from .engine import Engine  # noqa: PLC0415
        from .server import create_app  # noqa: PLC0415
        from .session import Session  # noqa: PLC0415

        self.folder = folder
        self._session = Session(folder)
        self._engine = Engine(self._session)
        self._sock = bind_local(0)
        self.url = f"http://{HOST}:{self._sock.getsockname()[1]}/"
        self._server = uvicorn.Server(
            uvicorn_config(create_app(self._session, self._engine), self._sock))
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._sock]},
            name="kuulas-server", daemon=True)
        self._thread.start()
        while not self._server.started and self._thread.is_alive():
            threading.Event().wait(0.02)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)
        self._sock.close()
        self._engine.close()
        self._session.close()


# -- the window -----------------------------------------------------

_MEDIA_TYPES = ("Audio and video (*.wav;*.flac;*.mp3;*.m4a;*.aac;*.ogg;*.opus;*.aif;"
                "*.aiff;*.mp4;*.mov;*.mkv;*.webm)", "All files (*.*)")


def load_webview():
    """The ``webview`` module, or None when the ``desktop`` extra is not installed."""
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        return None
    return webview


class Bridge:
    """Exposed to the page as ``window.pywebview.api``. Every public method is
    callable from JS; the window and state are underscore-private so pywebview
    does not try to expose (and walk) them."""

    def __init__(self, webview, recents: Path) -> None:
        self._webview = webview
        self._recents = recents
        self._window = None
        self._project: RunningProject | None = None

    # -- dialogs, for the page ---------------------------------------

    def _dialog(self, kind, **options) -> list[str]:
        if self._window is None:
            return []
        result = self._window.create_file_dialog(kind, **options)
        return [str(p) for p in result or []]

    def pick_media(self) -> list[str]:
        """Native import dialog: absolute paths, to be linked in place."""
        return self._dialog(self._webview.FileDialog.OPEN, allow_multiple=True,
                            file_types=_MEDIA_TYPES)

    def pick_save(self, name: str = "") -> str | None:
        got = self._dialog(self._webview.FileDialog.SAVE, save_filename=name)
        return got[0] if got else None

    def dropped(self, event: dict) -> None:
        """A file drop: pywebview gives full paths only here, on the Python side."""
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        if paths and self._window is not None:
            self._window.evaluate_js(
                "window.kuulasNative && "
                f"window.kuulasNative.importPaths({json.dumps(paths)})")

    # -- projects ----------------------------------------------------

    def recent(self) -> list[str]:
        return load_recents(self._recents)

    def choose_project(self) -> bool:
        got = self._dialog(self._webview.FileDialog.FOLDER)
        return bool(got) and self.open_project(got[0])

    def new_project(self) -> bool:
        got = self._dialog(self._webview.FileDialog.SAVE, save_filename="Untitled.kuulas")
        if not got:
            return False
        folder = got[0] if got[0].endswith(".kuulas") else got[0] + ".kuulas"
        return self.open_project(folder)

    def open_project(self, folder: str) -> bool:
        try:
            running = RunningProject(folder)
        except KuulasError as e:
            if self._window is not None:
                self._window.evaluate_js(f"alert({json.dumps(str(e))})")
            return False
        add_recent(self._recents, folder)
        previous, self._project = self._project, running
        self._window.set_title(window_title(folder))
        self._window.load_url(running.url)
        if previous is not None:
            previous.stop()
        return True

    def show_launcher(self) -> None:
        self._window.set_title(window_title(None))
        self._window.load_html(launcher_html(self.recent()))
        previous, self._project = self._project, None
        if previous is not None:
            previous.stop()

    def close(self) -> None:
        if self._project is not None:
            self._project.stop()
            self._project = None

    # -- the native menu ---------------------------------------------

    def menu(self, item_id: str) -> None:
        if item_id == "file.open":
            self.show_launcher()
        elif item_id == "window.minimize":
            self._window.minimize()
        elif self._project is not None:
            self._window.evaluate_js(
                f"window.kuulasNative && window.kuulasNative.menu({json.dumps(item_id)})")


def launcher_html(recent: list[str]) -> str:
    """The start page: recent projects and Open / New. Plain, no scripts but
    the calls into the bridge, and every string through ``t``."""
    rows = "".join(
        f'<li><button data-path="{html.escape(p, quote=True)}">'
        f"{html.escape(Path(p).name.removesuffix('.kuulas'))}</button>"
        f"<small>{html.escape(p)}</small></li>" for p in recent)
    empty = "" if recent else f"<p>{html.escape(t('desktop.launcher.none'))}</p>"
    return f"""<!doctype html><html lang="{html.escape(t('desktop.launcher.lang'))}">
<head><meta charset="utf-8"><title>kuulas</title>
<meta name="color-scheme" content="light dark">
<style>
body{{font:15px system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem}}
ul{{list-style:none;padding:0}} li{{margin:.6rem 0}} small{{display:block;opacity:.6}}
button{{font:inherit;padding:.35rem .8rem}} li button{{border:0;background:none;
color:LinkText;cursor:pointer;padding:0;font-size:1.05rem}}
</style></head><body>
<h1>kuulas</h1>
<p><button id="open">{html.escape(t('desktop.launcher.open'))}</button>
<button id="new">{html.escape(t('desktop.launcher.new'))}</button></p>
<h2>{html.escape(t('desktop.launcher.recent'))}</h2>{empty}<ul>{rows}</ul>
<script>
const api = () => window.pywebview.api;
document.getElementById("open").onclick = () => api().choose_project();
document.getElementById("new").onclick = () => api().new_project();
for (const b of document.querySelectorAll("li button"))
  b.onclick = () => api().open_project(b.dataset.path);
</script></body></html>"""


def _menu(bridge: Bridge) -> list:
    from webview.menu import Menu, MenuAction, MenuSeparator  # noqa: PLC0415

    def action(item):
        return MenuAction(item["label"], lambda: bridge.menu(item["id"]))

    return [Menu(m["label"], [MenuSeparator() if i is None else action(i)
                              for i in m["items"]])
            for m in localised_menu()]


def run_window(folder: str | None = None) -> int:
    """Open the window (the launcher, or ``folder`` straight away) and block until
    it closes. 1 with a message when the ``desktop`` extra is missing."""
    webview = load_webview()
    if webview is None:
        print(t("desktop.missing_extra"), file=sys.stderr)
        return 1
    bridge = Bridge(webview, recents_file())
    bridge._window = window = webview.create_window(
        window_title(folder), html=launcher_html(bridge.recent()),
        js_api=bridge, width=1400, height=900, min_size=(900, 600))

    def drop_handlers() -> None:
        # Registered on every page load: a navigation replaces the document.
        from webview.dom import DOMEventHandler  # noqa: PLC0415
        window.dom.document.events.drop += DOMEventHandler(
            bridge.dropped, prevent_default=True, stop_propagation=False)

    window.events.loaded += drop_handlers
    window.events.closed += bridge.close

    def start() -> None:
        if folder is not None:
            bridge.open_project(folder)

    webview.start(start, menu=_menu(bridge))
    bridge.close()
    return 0


def run_launcher() -> int:
    return run_window(None)
