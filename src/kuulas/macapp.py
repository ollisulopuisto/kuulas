"""Kuulas.app: a light macOS launcher that makes ``.kuulas`` folders open by
double-click (WP72 step 1).

A ``.kuulas`` project is a folder. Finder shows a folder as one file only if an
app declares a type that conforms to ``com.apple.package``, and opens it only if
that app receives the "open document" event. So this builds a small AppleScript
applet (``osacompile``): its ``on open`` handler runs the README's ``uvx`` command
for each project, in the background; ``on run`` (no document) opens the launcher.
No PyInstaller, no signing, built locally, nothing under ``/Applications``.

Everything that can be decided without a Mac is a pure function here (the plist
content, the shell and AppleScript quoting, which paths count as projects, whether
a project is already open on this computer). The build itself is
:func:`build_main`; ``scripts/make_app.py`` calls it.

This file is also run by the applet as a plain script (``python macapp.py check
<project>``), outside the kuulas environment: so it imports the standard library
only, and nothing from the ``kuulas`` package. The lock rules are copied from
``package.py`` and a test keeps the constants equal.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

BUNDLE_ID = "fi.sulopuisto.kuulas"
UTI = "fi.sulopuisto.kuulas.project"
EXTENSION = "kuulas"
APP_NAME = "Kuulas"
ICON_NAME = "kuulas"
DOC_ICON_NAME = "kuulas-doc"
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
              "LaunchServices.framework/Support/lsregister")

#: Same rules as ``package.py`` (a test keeps them equal): a lock of a process
#: on this machine whose heartbeat is older than STALE_S was left by a crash.
STALE_S = 120
LOCKS_DIR = "locks"

REPO = Path(__file__).resolve().parents[2]
ICONS = Path(__file__).resolve().parent / "assets" / "icons"

#: What the applet says. English and Finnish, chosen when the app is built.
MESSAGES = {
    "en": {
        "moved": "Kuulas cannot find its program folder:\n%s\n\nThe repository was "
                 "moved. Build the app again with scripts/make_app.py.",
        "invalid": "This is not a kuulas project (a folder ending in .kuulas with a "
                   "manifest.json):\n%s",
        "ok": "OK",
    },
    "fi": {
        "moved": "Kuulas ei löydä ohjelmakansiotaan:\n%s\n\nKoodivarasto on "
                 "siirretty. Rakenna sovellus uudelleen komennolla "
                 "scripts/make_app.py.",
        "invalid": "Tämä ei ole kuulas-projekti (.kuulas-päätteinen kansio, jossa "
                   "on manifest.json):\n%s",
        "ok": "OK",
    },
}


# -- projects ----------------------------------------------------------------------


def project_problem(path: str | Path) -> str | None:
    """Why ``path`` is not a kuulas project: "folder", "suffix" or "manifest";
    None when it is a folder ending in ``.kuulas`` holding a manifest.json."""
    folder = Path(str(path).rstrip("/") or "/")
    if not folder.is_dir():
        return "folder"
    if folder.suffix != f".{EXTENSION}":
        return "suffix"
    if not (folder / "manifest.json").is_file():
        return "manifest"
    return None


def _parse_iso(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def open_here(project: str | Path, host: str | None = None, *,
              is_alive: Callable[[int], bool] = _pid_alive,
              now: datetime | None = None) -> int | None:
    """The pid of the kuulas on this computer that has ``project`` open, or None.

    Read from the lock files (``locks/*.json``): a lock counts when it names this
    host, its heartbeat is fresh (``STALE_S``) and its process is alive. Locks of
    other computers (Dropbox) never count here; conflicted copies and half-synced
    files are skipped.
    """
    host = host or socket.gethostname()
    now = now or datetime.now(UTC)
    folder = Path(str(project).rstrip("/") or "/")
    best: tuple[float, int] | None = None
    for path in [folder / "lock.json", *sorted((folder / LOCKS_DIR).glob("*.json"))]:
        if "conflicted copy" in path.name.lower():
            continue
        try:
            lock = json.loads(path.read_text(encoding="utf-8"))
            age = (now - _parse_iso(lock["heartbeat_utc"])).total_seconds()
            pid = lock["pid"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if (lock.get("host") != host or not isinstance(pid, int) or pid <= 0
                or age >= STALE_S or not is_alive(pid)):
            continue
        if best is None or age < best[0]:
            best = (age, pid)
    return best[1] if best else None


# -- quoting and commands --------------------------------------------------------


def applescript_string(text: str) -> str:
    """``text`` as an AppleScript expression for that string: a literal, with each
    line break written as ``linefeed`` (a literal cannot hold one)."""
    def lit(part: str) -> str:
        return '"' + part.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return " & linefeed & ".join(lit(p) for p in text.replace("\r", "\n").split("\n"))


def launch_prefix(repo: str | Path, uvx: str) -> str:
    """The README command up to (not including) the project, shell-quoted."""
    spec = shlex.quote(f"{repo}[desktop]")
    return f"{shlex.quote(uvx)} --from {spec} --with-editable {spec} kuulas"


def launch_command(repo: str | Path, project: str | Path, uvx: str) -> str:
    """The full shell line that opens ``project`` in its own window."""
    return f"{launch_prefix(repo, uvx)} open {shlex.quote(str(project))} --window"


def tool_path(uvx: str) -> str:
    """PATH for the applet (it starts with almost none): where uv lives, the usual
    Homebrew and user bins (ffmpeg), then the system's."""
    home = Path.home()
    parts = [str(Path(uvx).parent) if "/" in uvx else "", str(home / ".local/bin"),
             str(home / ".cargo/bin"), "/opt/homebrew/bin", "/usr/local/bin",
             "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    seen: list[str] = []
    for p in parts:
        if p and p not in seen:
            seen.append(p)
    return ":".join(seen)


# -- the applet ------------------------------------------------------------------


def applet_source(repo: str | Path, uvx: str, uv: str, lang: str = "en") -> str:
    """The AppleScript the applet runs.

    ``on open`` asks the helper (this file, run with ``uv run --no-project``) about
    each dropped item: "invalid", "open <pid>" (already open here: bring that
    process forward instead of starting a second) or "ok" (start it, detached,
    log in ``~/Library/Logs/Kuulas.log``).
    """
    msg = MESSAGES.get(lang, MESSAGES["en"])
    repo = str(repo)
    q = applescript_string
    helper = f"{repo}/src/kuulas/macapp.py"
    return f"""-- Built by scripts/make_app.py (kuulas WP72). Do not edit: build again.
property repoPath : {q(repo)}
property uvPath : {q(uv)}
property helperPath : {q(helper)}
property toolPath : {q(tool_path(uvx))}
property launchPrefix : {q(launch_prefix(repo, uvx))}
property movedText : {q(msg["moved"])}
property invalidText : {q(msg["invalid"])}
property okText : {q(msg["ok"])}

on run
\tmy checkRepo()
\tmy start(launchPrefix & " desktop")
end run

on open theItems
\tmy checkRepo()
\trepeat with anItem in theItems
\t\tmy openOne(POSIX path of anItem)
\tend repeat
end open

on checkRepo()
\ttry
\t\tdo shell script "test -f " & quoted form of (repoPath & "/pyproject.toml")
\ton error
\t\tdisplay dialog (my fill(movedText, repoPath)) buttons {{okText}} \xac
\t\t\tdefault button 1 with icon stop
\t\terror number -128
\tend try
end checkRepo

on fill(template, value)
\tset AppleScript's text item delimiters to "%s"
\tset parts to text items of template
\tset AppleScript's text item delimiters to value
\tset joined to parts as text
\tset AppleScript's text item delimiters to ""
\treturn joined
end fill

on openOne(projectPath)
\tset runner to "export PATH=" & quoted form of toolPath & "; " & quoted form of uvPath
\tset runner to runner & " run --no-project --quiet --python 3.13 python "
\tset runner to runner & quoted form of helperPath & " check "
\tset verdict to do shell script runner & quoted form of projectPath
\tif verdict is "invalid" then
\t\tdisplay dialog (my fill(invalidText, projectPath)) buttons {{okText}} \xac
\t\t\tdefault button 1 with icon stop
\telse if verdict starts with "open " then
\t\t-- Already open on this computer: do not start a second one. Bring its
\t\t-- window forward (System Events asks for permission once).
\t\ttry
\t\t\tset thePid to (text 6 thru -1 of verdict) as integer
\t\t\ttell application "System Events"
\t\t\t\tset frontmost of (first process whose unix id is thePid) to true
\t\t\tend tell
\t\tend try
\telse
\t\tmy start(launchPrefix & " open " & quoted form of projectPath & " --window")
\tend if
end openOne

on start(command)
\tset logFile to " >> \\"$HOME/Library/Logs/Kuulas.log\\" 2>&1 &"
\tset prefix to "export PATH=" & quoted form of toolPath & "; nohup "
\tdo shell script prefix & command & logFile
end start
"""


# -- the bundle ------------------------------------------------------------------


def plist_keys() -> dict:
    """The Info.plist keys merged into the applet's own."""
    return {
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIconFile": ICON_NAME,
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Kuulas project",
            "CFBundleTypeRole": "Editor",
            "CFBundleTypeExtensions": [EXTENSION],
            "LSItemContentTypes": [UTI],
            "LSTypeIsGroup": False,
            "LSHandlerRank": "Owner",
            "CFBundleTypeIconFile": DOC_ICON_NAME,
        }],
        "UTExportedTypeDeclarations": [{
            "UTTypeIdentifier": UTI,
            "UTTypeDescription": "Kuulas project",
            "UTTypeConformsTo": ["com.apple.package", "public.composite-content"],
            "UTTypeIconFile": DOC_ICON_NAME,
            "UTTypeTagSpecification": {"public.filename-extension": [EXTENSION]},
        }],
    }


def find_tools() -> dict[str, str]:
    """Absolute paths of uvx and uv (the bare name when not found)."""
    return {name: shutil.which(name) or name for name in ("uvx", "uv")}


def plan(into: Path, repo: str | Path, *, register: bool,
         tools: dict[str, str]) -> list[str]:
    """What a build does, as lines of text (printed by ``--dry-run``)."""
    app = Path(into) / f"{APP_NAME}.app"
    steps = [
        f"repository : {repo}",
        f"uvx / uv   : {tools['uvx']} / {tools['uv']}",
        f"remove     : {app} (if it exists; rebuilding replaces it)",
        f"osacompile : AppleScript applet -> {app}",
        f"Info.plist : bundle id {BUNDLE_ID}, document type .{EXTENSION}, "
        f"exported type {UTI} (com.apple.package)",
        f"icons      : {ICONS / 'kuulas.icns'} -> Resources/{ICON_NAME}.icns and "
        f"{DOC_ICON_NAME}.icns",
        "codesign   : ad hoc re-sign (the plist edit broke the signature)",
    ]
    if register:
        steps += [f"register   : {LSREGISTER} -f {app}",
                  f"undo       : {LSREGISTER} -u {app}"]
    else:
        steps.append("register   : skipped (--no-register)")
    return steps


def ensure_icns(target: Path) -> Path:
    """The kuulas ``.icns``: the committed one, else made from the PNG set with
    ``iconutil`` into ``target``. SystemExit with a message when neither works."""
    committed = ICONS / "kuulas.icns"
    if committed.is_file():
        return committed
    iconutil = shutil.which("iconutil")
    if not iconutil:
        print(f"{committed} is missing and iconutil is not available; "
              "run scripts/make_icons.py on a Mac", file=sys.stderr)
        raise SystemExit(1)
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "kuulas.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            shutil.copy(ICONS / f"kuulas-{base}.png", iconset / f"icon_{base}x{base}.png")
            shutil.copy(ICONS / f"kuulas-{base * 2}.png",
                        iconset / f"icon_{base}x{base}@2x.png")
        subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(target)],  # noqa: S603
                       check=True)
    return target


def build(into: Path, *, register: bool, lang: str, tools: dict[str, str],
          repo: Path = REPO) -> Path:
    """Build ``Kuulas.app`` into ``into`` (replacing one there) and return it."""
    into = Path(into).expanduser()
    app = into / f"{APP_NAME}.app"
    into.mkdir(parents=True, exist_ok=True)
    if app.exists():
        shutil.rmtree(app)
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "kuulas.applescript"
        script.write_text(applet_source(repo, tools["uvx"], tools["uv"], lang),
                          encoding="utf-8")
        subprocess.run(["/usr/bin/osacompile", "-o", str(app), str(script)],  # noqa: S603
                       check=True)
        icns = ensure_icns(Path(tmp) / "kuulas.icns")
        res = app / "Contents" / "Resources"
        for old in ("applet.icns", "droplet.icns"):  # named by osacompile after the kind
            (res / old).unlink(missing_ok=True)
        shutil.copy(icns, res / f"{ICON_NAME}.icns")
        shutil.copy(icns, res / f"{DOC_ICON_NAME}.icns")
    info = app / "Contents" / "Info.plist"
    data = plistlib.loads(info.read_bytes())
    data.update(plist_keys())
    info.write_bytes(plistlib.dumps(data))
    if shutil.which("codesign"):
        subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(app)],  # noqa: S603, S607
                       check=False, capture_output=True)
    if register:
        subprocess.run([LSREGISTER, "-f", str(app)], check=True)  # noqa: S603
    return app


def build_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="make_app.py", description="Build Kuulas.app, the launcher that opens "
        ".kuulas folders by double-click (macOS).")
    parser.add_argument("--into", default="~/Applications",
                        help="folder to build Kuulas.app into (default ~/Applications)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan, change nothing")
    parser.add_argument("--no-register", action="store_true",
                        help="do not run lsregister (Finder learns the type later)")
    parser.add_argument("--lang", choices=sorted(MESSAGES),
                        default="fi" if os.environ.get("LANG", "").startswith("fi")
                        else "en", help="language of the app's messages")
    args = parser.parse_args(argv)
    into = Path(args.into).expanduser()
    tools = find_tools()
    lines = plan(into, REPO, register=not args.no_register, tools=tools)
    if args.dry_run:
        print("\n".join(lines))
        return 0
    if sys.platform != "darwin":
        print("Kuulas.app can only be built on macOS.", file=sys.stderr)
        return 1
    if str(into.resolve()) in ("/Applications", "/System/Applications"):
        print("Not building into /Applications (no sudo); use ~/Applications.",
              file=sys.stderr)
        return 1
    print("\n".join(lines))
    app = build(into, register=not args.no_register, lang=args.lang, tools=tools)
    print(f"built {app}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """``check <project>``: print invalid, ``open <pid>`` or ok (used by the applet)."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "check":
        if project_problem(args[1]) is not None:
            print("invalid")
        else:
            pid = open_here(args[1])
            print(f"open {pid}" if pid else "ok")
        return 0
    print("usage: macapp.py check <project>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
