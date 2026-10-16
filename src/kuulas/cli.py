"""The ``kuulas`` command: ``info <folder>`` (WP29) and ``open <folder>`` (WP3)."""

from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser

import uvicorn

from . import package
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
    from .server import create_app  # noqa: PLC0415
    from .session import Session  # noqa: PLC0415

    session = Session(folder)
    engine = Engine(session)
    sock = bind_local(port)
    try:
        url = f"http://{HOST}:{sock.getsockname()[1]}/"
        server = uvicorn.Server(uvicorn_config(create_app(session, engine), sock))
        print(t("cli.open.serving", path=folder, url=url))
        if browser:
            # Once the server accepts connections, not before: the first
            # request must not meet a closed port.
            def later() -> None:
                while not server.started and not server.should_exit:
                    threading.Event().wait(0.05)
                if server.started:
                    webbrowser.open(url)
            threading.Thread(target=later, daemon=True).start()
        server.run(sockets=[sock])
    finally:
        sock.close()
        engine.close()
        session.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kuulas", description=t("cli.description"))
    commands = parser.add_subparsers(dest="command", required=True)
    shown = commands.add_parser("info", help=t("cli.info.help"))
    shown.add_argument("folder", help=t("cli.info.folder"))
    opened = commands.add_parser("open", help=t("cli.open.help"))
    opened.add_argument("folder", help=t("cli.open.folder"))
    opened.add_argument("--port", type=int, default=0, help=t("cli.open.port"))
    opened.add_argument("--no-browser", action="store_true",
                        help=t("cli.open.no_browser"))
    args = parser.parse_args(argv)
    try:
        if args.command == "info":
            return info(args.folder)
        if args.command == "open":
            return open_project(args.folder, args.port, not args.no_browser)
    except KuulasError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
