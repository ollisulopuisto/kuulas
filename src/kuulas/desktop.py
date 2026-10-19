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

import base64
import html
import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import uvicorn

from .cli import HOST, bind_local, uvicorn_config
from .messages import KuulasError, t
from .openfiles import project_paths

log = logging.getLogger("kuulas.desktop")

#: Most recent first; older entries fall off.
MAX_RECENT = 20

#: The app icons, written by ``scripts/make_icons.py``.
ICON_DIR = Path(__file__).parent / "assets" / "icons"


def icon_path(kind: str) -> Path:
    """``"dock"``: the macOS-style icon with its margin; ``"window"``: the plain one."""
    return ICON_DIR / ("kuulas-dock.png" if kind == "dock" else "kuulas-256.png")


def set_dock_icon(platform: str | None = None, appkit: Any = ...) -> bool:
    """Show the kuulas icon in the macOS Dock. A window run from ``uv run`` is a
    Python process, so without this the Dock shows Python's rocket. True when it
    was set; False on other systems or when pyobjc is missing. Never raises."""
    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        return False
    if appkit is ...:
        try:
            import AppKit as appkit  # noqa: PLC0415, N813
        except ImportError:
            return False
    if appkit is None:
        return False
    try:
        image = appkit.NSImage.alloc().initWithContentsOfFile_(str(icon_path("dock")))
        appkit.NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:  # noqa: BLE001 - an icon is never worth a crash
        return False
    return True


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
    """The recent projects file: ``$KUULAS_RECENTS_FILE`` (tests, portable setups)
    or ``recent.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_RECENTS_FILE")
    return Path(override) if override else config_dir() / "recent.json"


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
        # The page may be gone already (pywebview does not always fire pagehide, and
        # a playing cursor is saved only every 5 s): write the engine's playhead.
        try:
            position = int(self._engine.status()["position"])
        except Exception as e:  # noqa: BLE001 - closing must go on whatever the engine says
            log.warning(t("log.desktop.position_unknown", error=str(e)))
            position = None
        self._session.flush_view(playhead=position)
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


def reveal_command(folder: str | Path, platform: str | None = None) -> list[str]:
    """The command that shows ``folder`` in the file manager: Finder (selected),
    Explorer (selected) or the default file manager. A list, never a shell line."""
    platform = platform or sys.platform
    path = str(folder)
    if platform == "darwin":
        return ["open", "-R", path]
    if platform.startswith("win"):
        return ["explorer", f"/select,{path}"]
    return ["xdg-open", path]


def _spawn(command: list[str]) -> None:
    subprocess.Popen(command)  # noqa: S603 - fixed program, path made by the exporter


class Bridge:
    """Exposed to the page as ``window.pywebview.api``. Every public method is
    callable from JS; the window and state are underscore-private so pywebview
    does not try to expose (and walk) them."""

    def __init__(self, webview, recents: Path) -> None:
        self._webview = webview
        self._recents = recents
        self._window = None
        self._project: RunningProject | None = None
        self._runner = _spawn

    @property
    def project_folder(self) -> str | None:
        """The project this window shows, or None on the launcher page."""
        return None if self._project is None else self._project.folder

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

    def choose_export_folder(self, start: str | None = None) -> str | None:
        """Native folder chooser for an export: the chosen folder, or None when
        cancelled. The page passes only a start hint (a string); it is not used
        as a path to write to, only as where the dialog opens, at the nearest
        folder that exists (the default ``<project> exports`` may not yet)."""
        if not isinstance(start, str) or not start or "\0" in start:
            return None
        folder = Path(start)
        while not folder.is_dir() and folder != folder.parent:
            folder = folder.parent
        got = self._dialog(self._webview.FileDialog.FOLDER, directory=str(folder))
        return got[0] if got else None

    def pick_project_folder(self) -> str | None:
        """Native folder chooser for "Open a project..." in the Clipboard tab:
        the chosen folder, or None when cancelled. It only names a folder; the
        server decides whether it is a project (``clipboard_browse.project_folder``)
        and only ever reads its ``clipboard.json``."""
        got = self._dialog(self._webview.FileDialog.FOLDER)
        return got[0] if got else None

    def reveal_export(self) -> bool:
        """Show the folder of the last "Export all tracks" in Finder / Explorer.
        Takes no argument: the page cannot name a path, only ask for the one the
        exporter made in this run."""
        folder = getattr(getattr(self._project, "_session", None),
                         "last_export_folder", None)
        if not folder or not Path(folder).is_dir():
            return False
        try:
            self._runner(reveal_command(folder))
        except OSError:
            return False
        return True

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
    mark = base64.b64encode((ICON_DIR / "kuulas-icon.svg").read_bytes()).decode()
    return f"""<!doctype html><html lang="{html.escape(t('desktop.launcher.lang'))}">
<head><meta charset="utf-8"><title>kuulas</title>
<meta name="color-scheme" content="light dark">
<style>
body{{font:15px system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem}}
ul{{list-style:none;padding:0}} li{{margin:.6rem 0}} small{{display:block;opacity:.6}}
h1{{display:flex;align-items:center;gap:.6rem}} .mark{{border-radius:22%}}
button{{font:inherit;padding:.35rem .8rem}} li button{{border:0;background:none;
color:LinkText;cursor:pointer;padding:0;font-size:1.05rem}}
</style></head><body>
<h1><img class="mark" alt="" width="40" height="40"
src="data:image/svg+xml;base64,{mark}"> kuulas</h1>
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


# -- several windows, and documents opened from Finder ---------------

#: ``NSApplicationDelegateReplySuccess``: tells AppKit the files were handled.
_REPLY_SUCCESS = 0


def make_open_files_method(callback):
    """The body of the delegate's ``application:openFiles:``. The event arrives on
    the Cocoa main thread, which must not wait for a server to start, so the paths
    go to ``callback`` on a worker thread; AppKit is told at once that they are
    handled (a failure to open one is shown in the window, not by Finder)."""

    def open_files(_self, nsapp, files):
        paths = [str(f) for f in files]
        threading.Thread(target=callback, args=(paths,), name="kuulas-open",
                         daemon=True).start()
        nsapp.replyToOpenOrPrint_(_REPLY_SUCCESS)

    return open_files


def install_open_files_hook(callback, platform: str | None = None, objc: Any = ...,
                            delegate_class: Any = ...) -> bool:
    """Make a double-clicked ``.kuulas`` folder reach ``callback(paths)``.

    pywebview owns the Cocoa loop and its own app delegate, which does not
    implement ``application:openFiles:``. Adding the method to that class (spiked in
    a Briefcase bundle, 2026-10-19: at launch and while running) is enough; call
    this before ``webview.start()``. True when installed; False off macOS or when
    PyObjC is missing. Never raises: opening from the dialog still works."""
    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        return False
    try:
        if objc is ...:
            import objc  # noqa: PLC0415
        if delegate_class is ...:
            from webview.platforms.cocoa import BrowserView  # noqa: PLC0415

            delegate_class = BrowserView.AppDelegate
        if objc is None or delegate_class is None:
            return False
        method = objc.selector(make_open_files_method(callback),
                               selector=b"application:openFiles:", signature=b"v@:@@")
        objc.classAddMethod(delegate_class, b"application:openFiles:", method)
    except Exception as e:  # noqa: BLE001 - a missing hook must not stop the window
        log.warning(t("log.desktop.open_hook_failed", error=str(e)))
        return False
    return True


class WindowApp:
    """The windows of one running app: the first is the launcher (or the project
    given on the command line); a project opened later, from Finder or the Dock,
    goes to the launcher window if it still shows the launcher, else to a new
    window. A project already open is brought forward, never opened twice (two
    servers on one project would fight over its lock). Documents that arrive
    before the first window is up wait for :meth:`ready`."""

    def __init__(self, webview, recents: Path, menu_factory=None) -> None:
        self._webview = webview
        self._recents = recents
        self._menu_factory = menu_factory
        self._lock = threading.RLock()
        self._bridges: list[Bridge] = []
        self._ready = False
        self._pending: list[str] = []

    def new_window(self, menu: bool = True) -> Bridge:
        """A window on the launcher page. ``menu=False`` for the first one, whose
        menu is the app menu given to ``webview.start``."""
        bridge = Bridge(self._webview, self._recents)
        options: dict[str, Any] = {}
        if menu and self._menu_factory is not None:
            options["menu"] = self._menu_factory(bridge)
        window = self._webview.create_window(
            window_title(None), html=launcher_html(bridge.recent()), js_api=bridge,
            width=1400, height=900, min_size=(900, 600), **options)
        bridge._window = window

        def drop_handlers() -> None:
            # Registered on every page load: a navigation replaces the document.
            from webview.dom import DOMEventHandler  # noqa: PLC0415
            window.dom.document.events.drop += DOMEventHandler(
                bridge.dropped, prevent_default=True, stop_propagation=False)

        def closed() -> None:
            bridge.close()
            with self._lock:
                if bridge in self._bridges:
                    self._bridges.remove(bridge)

        window.events.loaded += drop_handlers
        window.events.closed += closed
        with self._lock:
            self._bridges.append(bridge)
        return bridge

    def ready(self) -> None:
        """The first window exists: open what arrived while it did not."""
        with self._lock:
            self._ready = True
            pending, self._pending = self._pending, []
        self.open_paths(pending)

    def open_paths(self, paths) -> None:
        """Open the projects among ``paths`` (any thread)."""
        projects = project_paths(paths)
        with self._lock:
            if not self._ready:
                self._pending.extend(projects)
                return
        for folder in projects:
            self._open_one(folder)

    def _open_one(self, folder: str) -> None:
        with self._lock:
            for bridge in self._bridges:
                if bridge.project_folder == folder:
                    self._bring_forward(bridge)
                    return
            bridge = next((b for b in self._bridges if b.project_folder is None), None)
        if bridge is None:
            bridge = self.new_window()
        bridge.open_project(folder)

    @staticmethod
    def _bring_forward(bridge: Bridge) -> None:
        for name in ("restore", "show"):
            try:
                getattr(bridge._window, name)()
            except Exception as e:  # noqa: BLE001 - best effort, window may be gone
                log.debug("bring forward %s: %s", name, e)


def _menu(bridge: Bridge) -> list:
    from webview.menu import Menu, MenuAction, MenuSeparator  # noqa: PLC0415

    def action(item):
        return MenuAction(item["label"], lambda: bridge.menu(item["id"]))

    return [Menu(m["label"], [MenuSeparator() if i is None else action(i)
                              for i in m["items"]])
            for m in localised_menu()]


def run_window(folder: str | None = None) -> int:
    """Open the window (the launcher, or ``folder`` straight away) and block until
    the last window closes. 1 with a message when the ``desktop`` extra is missing."""
    webview = load_webview()
    if webview is None:
        print(t("desktop.missing_extra"), file=sys.stderr)
        return 1
    app = WindowApp(webview, recents_file(), _menu)
    bridge = app.new_window(menu=False)
    install_open_files_hook(app.open_paths)

    def start() -> None:
        set_dock_icon()
        if folder is not None:
            bridge.open_project(folder)
        app.ready()

    webview.start(start, menu=_menu(bridge), icon=str(icon_path("window")))
    bridge.close()
    return 0


def run_launcher() -> int:
    return run_window(None)
