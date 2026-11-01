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

import json
import logging
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn

from . import memory, offload
from . import live_engine
from .cli import HOST, bind_local, uvicorn_config
from .messages import KuulasError, t
from .new_project import SUFFIX, folder_name, project_path
from .openfiles import project_paths
from .recent_projects import (
    drop_missing,
    folder_size,
    insert_record,
    make_record,
    merge_record,
    normalize_record,
    remove_record,
    replace_path,
    update_record,
)

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


# The per-user folder lives in messages.py (a leaf module): the language setting is read
# while the first import of the app runs, long before this module can be loaded.
from .messages import config_dir  # noqa: E402


def recents_file() -> Path:
    """The recent projects file: ``$KUULAS_RECENTS_FILE`` (tests, portable setups)
    or ``recent.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_RECENTS_FILE")
    return Path(override) if override else config_dir() / "recent.json"


def webview_start_options(start_fn) -> dict:
    """Keyword arguments for ``webview.start``: a persistent web-storage folder instead
    of pywebview 5's private mode (belt and braces; the UI's settings themselves live
    in ``ui-prefs.json``, see ``ui_prefs``). Only what this pywebview accepts."""
    import inspect  # noqa: PLC0415
    wanted = {"private_mode": False, "storage_path": str(config_dir() / "webview")}
    try:
        accepted = inspect.signature(start_fn).parameters
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in wanted.items() if k in accepted}


_RECENTS_LOCK = threading.Lock()


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_records(file: Path) -> list[dict]:
    """Every record in the file, folders that are gone included. A missing or
    damaged file is an empty list."""
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    seen: set[str] = set()
    records: list[dict] = []
    for item in data:
        record = normalize_record(item)
        if record is not None and record["path"] not in seen:
            seen.add(record["path"])
            records.append(record)
    return records[:MAX_RECENT]


def _write_records(file: Path, records: list[dict]) -> None:
    """Written through a temp file and renamed, so a crash leaves the old list
    rather than half of a new one. A failure to write is swallowed: not
    remembering a project must not stop opening it."""
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        partial = file.with_name(file.name + ".tmp")
        partial.write_text(json.dumps(records[:MAX_RECENT], indent=1), encoding="utf-8")
        partial.replace(file)
    except OSError:
        return


def load_recent_records(file: Path) -> list[dict]:
    """The recent projects for the start page, most recent first: each record has
    ``exists`` (False when the folder is gone or unreachable, so the page can grey
    it out) and whatever was remembered of it. One stat per project; no project is
    opened or read."""
    return [{**r, "exists": Path(r["path"]).is_dir()} for r in _read_records(file)]


def load_recents(file: Path) -> list[str]:
    """The recent project folders that still exist, most recent first. A missing
    or damaged file is an empty list: the list is a convenience, never an error."""
    return [r["path"] for r in load_recent_records(file) if r["exists"]]


def add_recent(file: Path, folder: str, now: str | None = None) -> None:
    """Put ``folder`` first, stamped with the time it was opened (``now``, UTC ISO;
    the clock when None). What was remembered of the project stays. Folders that
    are gone stay in the list too, until they fall off the end, so the start page
    can show them as missing."""
    folder = str(Path(folder).resolve())
    record = make_record(folder, now or _now_utc())
    with _RECENTS_LOCK:
        _write_records(file, merge_record(_read_records(file), record, MAX_RECENT))


def set_recent_metadata(file: Path, folder: str, *, tracks: int | None = None,
                        duration_s: float | None = None, size: bool = True) -> None:
    """Remember what is known of ``folder`` for the start page: track count,
    length and (``size``) the size of the project folder, which is the ``.kuulas``
    folder only, linked media not counted, and left out when the tree is too big
    to walk. Order and opened time stay. Reads the project's folder, never
    writes in it; best effort."""
    folder = str(Path(folder).resolve())
    size_bytes = folder_size(folder) if size else None
    with _RECENTS_LOCK:
        records = _read_records(file)
        _write_records(file, update_record(
            records, folder, tracks=tracks, duration_s=duration_s,
            size_bytes=size_bytes))


# -- window title and menu ------------------------------------------


def window_title(folder: str | None) -> str:
    if not folder:
        return "kuulas"
    # Both separators: a Windows path is handled the same on any machine.
    name = folder.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    name = name.removesuffix(".kuulas")
    return t("desktop.title", name=name)


def menu_model() -> list[dict[str, Any]]:
    """Our own top-level menus in the native menu bar: none. The in-window bar is the
    one real menu (enabled states, modifier alternates, the Help search field), so the
    macOS bar keeps only what pywebview gives it: the app menu and the standard Edit
    and View (Cut/Copy/Paste/Select All for text fields, full screen)."""
    return []


# -- the server behind a window -------------------------------------


class RunningProject:
    """A project served on a free localhost port in a background thread: the
    same Session, Engine and app as ``kuulas open``. ``stop`` shuts it down and
    closes the project, so closing the window leaves nothing running."""

    def __init__(self, folder: str) -> None:
        # Imported here: the engine pulls in the audio libraries.
        from .engine import Engine  # noqa: PLC0415
        from .record_session import RecordSession  # noqa: PLC0415
        from .server import create_app  # noqa: PLC0415
        from .session import Session  # noqa: PLC0415

        self.folder = folder
        #: Called with ``summary()`` once the project is closed (the Bridge's hook to
        #: refresh the recents record); never allowed to stop the close.
        self.on_stopped = None
        self._session = Session(folder)
        self._engine = Engine(self._session)
        # Only a viewer of the recorder (WP12a): closing the window never stops a take.
        self._recorder = RecordSession(
            self._session, live_engine_factory=live_engine.factory_or_none())
        self._sock = bind_local(0)
        self.url = f"http://{HOST}:{self._sock.getsockname()[1]}/"
        self._server = uvicorn.Server(uvicorn_config(
            create_app(self._session, self._engine, recorder=self._recorder), self._sock))
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._sock]},
            name="kuulas-server", daemon=True)
        self._thread.start()
        while not self._server.started and self._thread.is_alive():
            threading.Event().wait(0.02)

    @property
    def session(self):
        """The project's Session: what another window of this app talks to."""
        return self._session

    def summary(self) -> dict:
        """Track count and length (seconds) of the project as it is now. Never raises."""
        try:
            state = self._session.history.state
            return {"tracks": len(state.tracks), "duration_s": state.length / state.rate}
        except Exception as e:  # noqa: BLE001 - a number on the start page is optional
            log.debug("project summary: %s", e)
            return {}

    def record_busy(self) -> str | None:
        """Why this project must not be closed now: ``"recording"`` while a take of it
        records (or one was heard recording and the recorder cannot be asked),
        ``"armed"`` while the microphone listens for pre-roll; None when nothing holds
        it. Closing never walks away from a take (ground rule 17). Never raises."""
        try:
            heard = self._recorder.recording_now()
            view = self._recorder.status()
        except Exception as e:  # noqa: BLE001 - a recorder that cannot be asked
            log.debug("record state: %s", e)
            return None
        if view.get("recording") and view.get("ours"):
            return "recording"
        if heard and view.get("available") is False:
            return "recording"
        if view.get("armed"):
            return "armed"
        return None

    def stop(self) -> None:
        summary = self.summary()
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
        self._recorder.close()
        self._engine.close()
        self._session.close()
        if self.on_stopped is not None:
            try:
                self.on_stopped(summary)
            except Exception as e:  # noqa: BLE001 - recents are a convenience
                log.debug("recents refresh: %s", e)


# -- the window -----------------------------------------------------

_MEDIA_TYPES = ("Audio and video (*.wav;*.flac;*.mp3;*.m4a;*.aac;*.ogg;*.opus;*.aif;"
                "*.aiff;*.mp4;*.mov;*.mkv;*.webm)", "All files (*.*)")


_NHSX_TYPES = ("Hindenburg session (*.nhsx)", "All files (*.*)")


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

    if path.startswith("-"):
        path = "./" + path

    if platform == "darwin":
        return ["open", "-R", path]
    if platform.startswith("win"):
        return ["explorer", f"/select,{path}"]
    return ["xdg-open", path]


def clipboard_command(platform: str | None = None) -> list[str]:
    """The program that reads the system clipboard's new text from stdin. A list."""
    platform = platform or sys.platform
    if platform == "darwin":
        return ["pbcopy"]
    if platform.startswith("win"):
        return ["clip"]
    return ["xclip", "-selection", "clipboard"]


def _pipe_to(command: list[str], text: str) -> None:
    subprocess.run(command, input=text.encode(), check=True, timeout=5)  # noqa: S603 - fixed program


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
        self._copier = _pipe_to
        #: Opens a folder in a window of its own (``WindowApp._open_one``); None when the
        #: bridge has no app around it, then the folder opens in this window.
        self._opener = None
        #: The ``WindowApp`` this window belongs to (the other windows are reached through
        #: it); None when the bridge stands alone.
        self._app = None

    @property
    def project_folder(self) -> str | None:
        """The project this window shows, or None on the launcher page."""
        return None if self._project is None else self._project.folder

    # -- dialogs, for the page ---------------------------------------

    def _dialog(self, kind, **options) -> list[str]:
        if self._window is None:
            return []
        result = self._window.create_file_dialog(kind, **options)
        if isinstance(result, str):
            # pywebview on macOS answers a SAVE dialog with one str, not a tuple.
            result = [result]
        return [str(p) for p in result or []]

    def pick_media(self) -> list[str]:
        """Native import dialog: absolute paths, to be linked in place."""
        return self._dialog(self._webview.FileDialog.OPEN, allow_multiple=True,
                            file_types=_MEDIA_TYPES)

    def pick_nhsx(self) -> str | None:
        """Native chooser for File > Import Hindenburg session: the one .nhsx file, or
        None when cancelled. It only names a file; the server reads it and finds the
        recordings."""
        got = self._dialog(self._webview.FileDialog.OPEN, file_types=_NHSX_TYPES)
        return got[0] if got else None

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

    def pick_orukeet_model(self) -> str | None:
        """Choose an existing local model; the setup API validates it before use."""
        got = self._dialog(self._webview.FileDialog.FOLDER)
        return got[0] if got else None

    def pick_project_folder(self) -> str | None:
        """Native folder chooser for "Open a project..." in the Clipboard tab:
        the chosen folder, or None when cancelled. It only names a folder; the
        server decides whether it is a project (``clipboard_browse.project_folder``)
        and only ever reads its ``clipboard.json``."""
        got = self._dialog(self._webview.FileDialog.FOLDER)
        return got[0] if got else None

    def copy_text(self, text: str) -> bool:
        """Put a short text (the shown time) on the system clipboard, for when the web
        view blocks navigator.clipboard. False when it could not."""
        if not isinstance(text, str) or len(text) > 200:
            return False
        try:
            self._copier(clipboard_command(), text)
        except (OSError, subprocess.SubprocessError):
            return False
        return True

    def reveal_automix_log(self) -> bool:
        """Show the newest automixer log file in Finder / Explorer. Takes no argument,
        like ``reveal_export``: the page asks for "the log", never names a path."""
        kept = getattr(getattr(self._project, "_session", None),
                       "last_automix_log", None)
        if not kept or not Path(kept).is_file():
            return False
        try:
            self._runner(reveal_command(kept))
        except OSError:
            return False
        return True

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

    def recent_records(self) -> list[dict]:
        return load_recent_records(self._recents)

    def choose_project(self) -> bool:
        got = self._dialog(self._webview.FileDialog.FOLDER)
        return bool(got) and self.open_project(got[0])

    def new_project(self) -> bool:
        got = self._dialog(self._webview.FileDialog.SAVE, save_filename="Untitled.kuulas")
        if not got:
            return False
        folder = got[0] if got[0].endswith(".kuulas") else got[0] + ".kuulas"
        return self.open_project(folder)

    def import_nhsx_project(self) -> bool:
        """Start screen: import a session into a new project, then open it."""
        from .cli import import_nhsx  # noqa: PLC0415 - reuse the headless import path

        got = self._dialog(self._webview.FileDialog.OPEN,
                           file_types=(t("desktop.nhsx.file_type"),))
        if not got:
            return False
        source = Path(got[0])
        chosen = self._dialog(self._webview.FileDialog.SAVE,
                              save_filename=source.stem + SUFFIX)
        if not chosen:
            return False
        try:
            typed = Path(chosen[0]).expanduser()
            target = project_path(str(typed.parent), typed.name)
            # Exclusive creation: the native Save dialog must never append to an
            # existing project, even if another process created it meanwhile.
            target.mkdir()
            import_nhsx(str(source), str(target))
        except (KuulasError, OSError, ValueError) as error:
            if self._window is not None:
                self._window.evaluate_js(f"alert({json.dumps(str(error))})")
            return False
        return self._open_in_window(str(target))

    def _open_in_window(self, folder: str) -> bool:
        if self._opener is None:
            return self.open_project(folder)
        self._opener(folder)
        return True

    def new_project_in_window(self) -> bool:
        """File > New project... : a native save dialog for the name and the folder,
        then the empty project opens in a window of its own (this one keeps its
        project). False when cancelled or the name cannot be a folder (the page is
        told)."""
        got = self._dialog(self._webview.FileDialog.SAVE,
                           save_filename="Untitled" + SUFFIX)
        if not got:
            return False
        chosen = Path(got[0])
        try:
            folder = chosen.with_name(folder_name(chosen.name))
        except KuulasError as e:
            if self._window is not None:
                self._window.evaluate_js(f"alert({json.dumps(str(e))})")
            return False
        return self._open_in_window(str(folder))

    def open_project_in_window(self) -> bool:
        """File > Open project... : a native folder chooser, then that project opens in a
        window of its own."""
        got = self._dialog(self._webview.FileDialog.FOLDER)
        return bool(got) and self._open_in_window(got[0])

    def open_path_in_window(self, folder: object) -> bool:
        """A project the server has just made (Series > New episode from series…) opens
        in a window of its own. Only an absolute path to a ``.kuulas`` folder with a
        manifest: the page cannot point this at anything else."""
        if not isinstance(folder, str) or not folder.strip() or "\0" in folder:
            return False
        path = Path(folder)
        if (not path.is_absolute() or path.suffix.lower() != SUFFIX
                or not (path / "manifest.json").is_file()):
            return False
        return self._open_in_window(str(path))

    def open_project(self, folder: str) -> bool:
        if not isinstance(folder, str) or not folder.strip() or "\0" in folder:
            return False

        # A project another window already shows comes forward instead (two writers on one
        # history would fork it).
        if self._app is not None and self._app.bring_forward_if_open(folder):
            return True
        try:
            # Not resolve(): a symlinked folder (a Dropbox link) keeps the chosen path.
            folder_path = Path(folder).expanduser()
            running = RunningProject(str(folder_path))
        except (KuulasError, OSError, RuntimeError) as e:
            if self._window is not None:
                self._window.evaluate_js(f"alert({json.dumps(str(e))})")
            return False
        add_recent(self._recents, folder)
        running.on_stopped = lambda summary: set_recent_metadata(
            self._recents, folder, **summary)
        # The size walk can take a while on a slow disk: not on the opening path.
        threading.Thread(
            target=set_recent_metadata, args=(self._recents, folder),
            kwargs=running.summary(), name="kuulas-recents", daemon=True).start()
        previous, self._project = self._project, running
        self._window.set_title(window_title(folder))
        self._window.load_url(running.url)
        if previous is not None:
            previous.stop()
        return True

    def open_recent_in_window(self, folder: str) -> bool:
        """File > Open Recent: the project opens in a window of its own (as Open project
        does). False when the folder is gone (the page says so; the menu greys it out)."""
        if not Path(folder).is_dir():
            return False
        return self._open_in_window(folder)

    def clear_recent(self) -> bool:
        """File > Open Recent > Clear menu: the start page's list too. The projects are
        not touched."""
        with _RECENTS_LOCK:
            _write_records(self._recents, [])
        return True

    def remove_recent(self, folder: object) -> bool:
        """Start page: drop one entry from the recent list. Only the list changes: the
        project folder and its media are never touched. False when it was not listed
        (so a second call is harmless)."""
        if not isinstance(folder, str) or not folder:
            return False
        with _RECENTS_LOCK:
            records = _read_records(self._recents)
            kept = remove_record(records, folder)
            if len(kept) == len(records):
                return False
            _write_records(self._recents, kept)
        return True

    def remove_missing_recents(self) -> int:
        """Remove every entry whose folder is gone from the list; returns how many.
        List entries only: nothing on disk is touched."""
        with _RECENTS_LOCK:
            records = _read_records(self._recents)
            kept = drop_missing(records, lambda p: Path(p).is_dir())
            if len(kept) != len(records):
                _write_records(self._recents, kept)
        return len(records) - len(kept)

    def restore_recent(self, record: object, index: object = 0) -> bool:
        """Undo of a removal: the record goes back where it was."""
        clean = normalize_record(record)
        if clean is None or not isinstance(record, dict):
            return False
        at = index if isinstance(index, int) and not isinstance(index, bool) else 0
        with _RECENTS_LOCK:
            _write_records(self._recents, insert_record(
                _read_records(self._recents), clean, at, MAX_RECENT))
        return True

    def locate_recent(self, folder: object) -> bool:
        """Start page, "Locate...": choose where a moved project is now. The entry
        keeps its place and facts and points at the new folder; the start page is
        redrawn. Only a folder with a manifest is accepted. False when cancelled or
        refused. The project itself is not opened, read or changed."""
        if not isinstance(folder, str) or not folder:
            return False
        got = self._dialog(self._webview.FileDialog.FOLDER)
        if not got:
            return False
        chosen = Path(got[0])
        if not (chosen / "manifest.json").is_file():
            if self._window is not None:
                self._window.evaluate_js(
                    f"alert({json.dumps(t('desktop.launcher.locate_refused'))})")
            return False
        with _RECENTS_LOCK:
            _write_records(self._recents, replace_path(
                _read_records(self._recents), folder, str(chosen.resolve())))
        self.show_launcher()
        return True

    def other_windows(self) -> list[dict]:
        """The other windows of this app that show a project, as ``{folder, name}``:
        where Edit > Clipboard > Copy to other window can send an entry."""
        if self._app is None:
            return []
        return [{"folder": b.project_folder, "name": Path(b.project_folder).stem}
                for b in self._app.project_windows() if b is not self]

    def send_to_window(self, folder: str, entry: dict) -> dict:
        """Put ``entry`` (a clipboard view of this project) on the clipboard of the
        project open in another window of this app, and tell that window so it can say
        what came and how to paste it. The adopted copy is the other project's own (the
        normal paste, with its recording check, then works); this project's entry stays.
        ``{ok: False, reason: "gone"}`` when no such other window is open any more."""
        target = None
        if self._app is not None:
            target = next((b for b in self._app.project_windows()
                           if b is not self and b.project_folder == folder), None)
        if target is None or self._project is None:
            return {"ok": False, "reason": "gone"}
        view = target._project.session.clipboard_adopt(entry, self._project.folder)
        note = {"from": Path(self._project.folder).stem, "entry": view}
        try:
            target._window.evaluate_js(
                "window.kuulasClipboardArrived&&window.kuulasClipboardArrived("
                f"{json.dumps(note)})")
        except Exception as e:  # noqa: BLE001 - the entry is there; the page may be mid-load
            log.debug("tell the other window: %s", e)
        return {"ok": True, "name": Path(target.project_folder).stem}

    def minimise(self) -> None:
        """View > Minimise (Cmd+M): the window goes to the Dock."""
        if self._window is not None:
            self._window.minimize()

    def close_project(self) -> dict:
        """File > Close project (Cmd+W): back to the start page. Every edit is already
        on disk and a transcription runs in its own process, so nothing is lost; but a
        running take or an armed microphone refuses it (``reason``)."""
        if self._project is not None:
            busy = self._project.record_busy()
            if busy:
                return {"closed": False, "reason": busy}
        self.show_launcher()
        return {"closed": True}

    def show_launcher(self) -> None:
        self._window.set_title(window_title(None))
        self._window.load_html(launcher_html(self.recent_records()))
        previous, self._project = self._project, None
        if previous is not None:
            previous.stop()

    def close(self) -> None:
        if self._project is not None:
            self._project.stop()
            self._project = None


def launcher_html(recent: list) -> str:
    """The start page: recent projects (records or bare paths) and Open / New.
    See :mod:`kuulas.launcher_page`."""
    from .launcher_page import launcher_html as page  # noqa: PLC0415

    return page(recent)


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


def _same_folder(a: str, b: str) -> bool:
    """Whether two paths name one folder (symlinks and aliases followed)."""
    try:
        return Path(a).resolve() == Path(b).resolve()
    except (OSError, RuntimeError, ValueError):
        return a == b


class WindowApp:
    """The windows of one running app: the first is the launcher (or the project
    given on the command line); a project opened later, from Finder or the Dock,
    goes to the launcher window if it still shows the launcher, else to a new
    window. A project already open is brought forward, never opened twice (two
    servers on one project would fight over its lock). Documents that arrive
    before the first window is up wait for :meth:`ready`."""

    def __init__(self, webview, recents: Path) -> None:
        self._webview = webview
        self._recents = recents
        self._lock = threading.RLock()
        self._bridges: list[Bridge] = []
        self._ready = False
        self._pending: list[str] = []

    def new_window(self) -> Bridge:
        """A window on the launcher page."""
        bridge = Bridge(self._webview, self._recents)
        window = self._webview.create_window(
            window_title(None), html=launcher_html(bridge.recent_records()),
            js_api=bridge,
            width=1400, height=900, min_size=(900, 600))
        bridge._window = window
        bridge._opener = self._open_one
        bridge._app = self

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

    def project_windows(self) -> list[Bridge]:
        """The windows that show a project now (not the launcher page)."""
        with self._lock:
            return [b for b in self._bridges if b.project_folder is not None]

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

    def bring_forward_if_open(self, folder: str) -> bool:
        """Bring the window that shows ``folder`` forward; False when none does. The
        same folder reached by a symlink, an alias or a trailing slash is the same
        project, so the paths are compared resolved."""
        with self._lock:
            for bridge in self._bridges:
                if bridge.project_folder is not None and _same_folder(
                        bridge.project_folder, folder):
                    self._bring_forward(bridge)
                    return True
        return False

    def _open_one(self, folder: str) -> None:
        log.info(t("log.desktop.opening", path=folder))
        if self.bring_forward_if_open(folder):
            return
        with self._lock:
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


def run_window(folder: str | None = None) -> int:
    """Open the window (the launcher, or ``folder`` straight away) and block until
    the last window closes. 1 with a message when the ``desktop`` extra is missing."""
    webview = load_webview()
    if webview is None:
        print(t("desktop.missing_extra"), file=sys.stderr)
        return 1
    # Analysis workers an earlier run left behind (a crash) go first.
    offload.start_sweep()
    memory.start_rss_watch()
    app = WindowApp(webview, recents_file())
    bridge = app.new_window()
    install_open_files_hook(app.open_paths)

    def start() -> None:
        set_dock_icon()
        if folder is not None:
            bridge.open_project(folder)
        app.ready()

    webview.start(start, icon=str(icon_path("window")),
                  **webview_start_options(webview.start))
    bridge.close()
    return 0


def run_launcher() -> int:
    return run_window(None)
