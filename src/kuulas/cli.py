"""The ``kuulas`` command: ``info <folder>`` (WP29), ``stats <folder>`` (WP70),
``open <folder>`` (WP3),
``import-nhsx <file> <folder>`` (WP13) and, without arguments, the desktop window
(WP15)."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from . import diag, export_formats, logsetup, offload, package, profiler
from .build_info import build_label
from .messages import KuulasError, t

#: The server answers this machine only: the API can change and delete a
#: project, and has no login. Never a wildcard address.
HOST = "127.0.0.1"


def _mb(size: int) -> str:
    return f"{size / 1e6:.1f}"


def info(folder: str) -> int:
    data = package.info(folder)
    m = data["manifest"]
    print(t("cli.info.project", path=folder, format=m.get("format"),
            version=m.get("version"), min_reader=m.get("min_reader"),
            written_by=m.get("written_by"), id=m.get("id")))
    for name, size in data["sizes"].items():
        print(t("cli.info.size", name=name, size_mb=_mb(size)))
    print(t("cli.info.media", **data["media"]))
    print(t("cli.info.backups", count=data["backups"]))
    return 0


def stats(folder: str, as_json: bool = False) -> int:
    """Print the session's statistics (WP70) without opening a window or taking
    the project's lock: the history is read-only, so a project open elsewhere is fine."""
    from . import project_stats  # noqa: PLC0415
    from .history import History  # noqa: PLC0415

    path = Path(folder).expanduser()
    manifest = package.read_manifest(path) if path.is_dir() else None
    if manifest is None or manifest.get("format") != package.FORMAT_NAME:
        raise KuulasError("error.package.not_a_project", path=folder)
    history = History(path / "project.sqlite", read_only=True)
    try:
        data = project_stats.gather(history, path)
    finally:
        history.close()
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(project_stats.to_text(data, t("stats.title", name=path.stem)), end="")
    return 0


def import_nhsx(nhsx_path: str, folder: str | None = None) -> int:
    """Import a Hindenburg session into the project (created if missing).
    Without a folder the project is ``<session name>.kuulas`` beside the session."""
    from .session import Session  # noqa: PLC0415

    source = Path(nhsx_path).expanduser()
    target = Path(folder).expanduser() if folder else source.with_suffix(".kuulas")
    if not source.is_file() or (target.exists() and not target.is_dir()):
        raise KuulasError("error.import.nhsx_failed", path=str(source))
    folder = str(target)
    session = Session(folder)
    try:
        session.command("import_nhsx", {"path": nhsx_path})
        print(t("cli.import_nhsx.done", path=folder, tracks=len(session.state.tracks),
                media=len(session.state.media),
                 clipboard=session.last_import_clipboard))
    finally:
        session.close()
    return 0


def _export_cli(folder: str, args: dict, tracks: bool) -> int:
    """Run one export without a window or server and print where it went. A
    project open in a window is read-only here, and the export refuses, saying
    who holds it."""
    from .session import Session  # noqa: PLC0415

    if not Path(folder).expanduser().is_dir():
        raise KuulasError("error.cli.not_a_project", path=folder)
    session = Session(str(Path(folder).expanduser()))
    try:
        last = -1

        def progress(fraction: float, _message: str) -> None:
            nonlocal last
            step = int(fraction * 10) * 10
            if step > last:
                last = step
                print(t("cli.export_tracks.progress", percent=step), flush=True)

        result = session.export(
            session.tracks_export_args(args) if tracks else session.mix_export_args(args),
            progress=progress)
        if tracks:
            print(t("cli.export_tracks.done", count=result["track_count"],
                    path=result["path"]))
            for path in result["paths"]:
                print(path)
            if result["silent"]:
                print(t("cli.export_tracks.silent", count=len(result["silent"]),
                        names=", ".join(result["silent"])))
        else:
            print(t("cli.export_mix.done", path=result["path"]))
            print(result["path"])
    finally:
        session.close()
    return 0


def list_formats() -> int:
    """The export formats this machine's ffmpeg can write, one id per line."""
    for fmt in export_formats.available_formats():
        print(fmt.id)
    return 0


def export_tracks(folder: str, out: str | None = None, fmt: str | None = None,
                  bit_depth: int | None = None, kbps: int | None = None) -> int:
    """Export every track of a project as a file. ``out`` is the folder the
    export folder goes into (default: ``<project> exports`` beside the project)."""
    return _export_cli(folder, {"folder": out, "format": fmt, "bit_depth": bit_depth,
                                "kbps": kbps}, tracks=True)


def export_mix(folder: str, out: str | None = None, fmt: str | None = None,
               bit_depth: int | None = None, kbps: int | None = None) -> int:
    """Export the mix of a project as one file in ``out`` (default: ``<project>
    exports`` beside the project)."""
    return _export_cli(folder, {"folder": out, "format": fmt, "bit_depth": bit_depth,
                                "kbps": kbps}, tracks=False)


def bind_local(port: int = 0) -> socket.socket:
    """A listening socket on 127.0.0.1; port 0 takes a free one. Handing the
    socket to uvicorn (rather than a port number) leaves no gap in which
    another process could take the port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
        sock.listen(128)
    except OSError:
        sock.close()
        raise
    return sock


def uvicorn_config(app, sock: socket.socket) -> uvicorn.Config:
    return uvicorn.Config(app, host=HOST, port=sock.getsockname()[1],
                          log_level="warning", ws_ping_interval=20)


def open_project(folder: str, port: int = 0, browser: bool = True) -> int:
    """Open (or create) the project and serve it until interrupted."""
    # Imported here: the engine pulls in the audio libraries, which `info` does not need.
    from .engine import Engine  # noqa: PLC0415
    from .record_session import RecordSession  # noqa: PLC0415
    from .server import create_app  # noqa: PLC0415
    from .session import Session  # noqa: PLC0415

    # Analysis workers an earlier run left behind (a crash) go first.
    offload.start_sweep()
    session = Session(folder)
    engine = Engine(session)
    # Only a viewer of the recorder: closing it below never stops a take.
    recorder = RecordSession(session)
    sock = bind_local(port)
    try:
        url = f"http://{HOST}:{sock.getsockname()[1]}/"
        server = uvicorn.Server(uvicorn_config(
            create_app(session, engine, recorder=recorder), sock))
        print(t("cli.open.serving", path=folder, url=url))
        if browser:
            # Once the server accepts connections, not before: the first
            # request must not meet a closed port.
            def later() -> None:
                while not server.started and not server.should_exit:
                    threading.Event().wait(0.05)
                if server.started:
                    webbrowser.open(url)
            threading.Thread(target=later, daemon=True,
                             name="kuulas-open-browser").start()
        server.run(sockets=[sock])
    finally:
        sock.close()
        recorder.close()
        engine.close()
        session.close()
    return 0


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911
    parser = argparse.ArgumentParser(prog="kuulas", description=t("cli.description"))
    parser.add_argument("--selftest", action="store_true", help=t("cli.selftest.help"))
    commands = parser.add_subparsers(dest="command")
    desktop_parser = commands.add_parser("desktop", help=t("cli.desktop.help"))
    shown = commands.add_parser("info", help=t("cli.info.help"))
    shown.add_argument("folder", help=t("cli.info.folder"))
    counted = commands.add_parser("stats", help=t("cli.stats.help"))
    counted.add_argument("folder", help=t("cli.info.folder"))
    counted.add_argument("--json", action="store_true", help=t("cli.stats.json"))
    imported = commands.add_parser("import-nhsx", help=t("cli.import_nhsx.help"))
    imported.add_argument("nhsx", help=t("cli.import_nhsx.nhsx"))
    imported.add_argument("folder", nargs="?", help=t("cli.import_nhsx.folder"))
    format_ids = [f.id for f in export_formats.ALL_FORMATS]
    exported = commands.add_parser("export-tracks", help=t("cli.export_tracks.help"))
    exported.add_argument("folder", nargs="?", help=t("cli.export_tracks.folder"))
    exported.add_argument("--list-formats", action="store_true",
                          help=t("cli.export_tracks.list_formats"))
    mixed = commands.add_parser("export-mix", help=t("cli.export_mix.help"))
    mixed.add_argument("folder", help=t("cli.export_tracks.folder"))
    for sub in (exported, mixed):
        sub.add_argument("--out", help=t("cli.export_tracks.out"))
        sub.add_argument("--format", choices=format_ids, metavar="FORMAT",
                         help=t("cli.export_tracks.format",
                                formats=", ".join(format_ids)))
        sub.add_argument("--bit-depth", type=int, choices=[16, 24, 32],
                         help=t("cli.export_tracks.bit_depth"))
        sub.add_argument("--kbps", type=int, help=t("cli.export_tracks.kbps"))
    opened = commands.add_parser("open", help=t("cli.open.help"))
    opened.add_argument("folder", help=t("cli.open.folder"))
    opened.add_argument("--port", type=int, default=0, help=t("cli.open.port"))
    opened.add_argument("--no-browser", action="store_true",
                        help=t("cli.open.no_browser"))
    for sub in (opened, desktop_parser):
        sub.add_argument("--debug", action="store_true", help=t("cli.debug.help"))
    opened.add_argument("--window", action="store_true", help=t("cli.open.window"))
    args = parser.parse_args(argv)
    if args.selftest:
        from . import selftest  # noqa: PLC0415

        return selftest.run()
    if getattr(args, "debug", False):
        diag.enable()
        diag.emit(f"kuulas debug: build {build_label()}")
    if args.command in (None, "desktop", "open"):
        # The windows and the server: the log level (KUULAS_LOG_LEVEL, else the saved
        # setting) and a recording from start-up (KUULAS_PROFILE=<seconds>).
        logsetup.apply(logsetup.resolve(os.environ, logsetup.level_setting()),
                       console=True)
        profiler.start_from_environment(os.environ)
    try:
        if args.command in (None, "desktop"):
            from . import desktop  # noqa: PLC0415

            return desktop.run_launcher()
        if args.command == "info":
            return info(args.folder)
        if args.command == "stats":
            return stats(args.folder, args.json)
        if args.command == "import-nhsx":
            return import_nhsx(args.nhsx, args.folder)
        if args.command == "export-tracks" and args.list_formats:
            return list_formats()
        if args.command in {"export-tracks", "export-mix"}:
            if not args.folder:
                parser.error(t("cli.export_tracks.need_folder"))
            run_export = export_tracks if args.command == "export-tracks" else export_mix
            return run_export(args.folder, args.out, args.format, args.bit_depth,
                              args.kbps)
        if args.command == "open" and args.window:
            from . import desktop  # noqa: PLC0415

            return desktop.run_window(args.folder)
        if args.command == "open":
            return open_project(args.folder, args.port, not args.no_browser)
    except KuulasError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
