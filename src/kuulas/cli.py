"""The ``kuulas`` command. Today only ``kuulas info <folder>`` (WP29); ``open``
and the server come with WP3."""

from __future__ import annotations

import argparse
import sys

from . import package
from .messages import KuulasError, t


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kuulas", description=t("cli.description"))
    commands = parser.add_subparsers(dest="command", required=True)
    shown = commands.add_parser("info", help=t("cli.info.help"))
    shown.add_argument("folder", help=t("cli.info.folder"))
    args = parser.parse_args(argv)
    try:
        if args.command == "info":
            return info(args.folder)
    except KuulasError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
