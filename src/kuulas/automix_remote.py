"""Run the automixer on another Mac over ssh and rsync ("Run on another Mac").

kuulas runs on a laptop, the render is faster on the Mac Studio. Nothing here is new
technology: the stock ``ssh`` and ``rsync`` (no new dependency), in the shape of the Colab
precedent (``colab_transcribe``): ship the data, run the tool, pull the result back, clean
up. ``automix.run`` calls this module after the local stems export when the settings say
``remote.enabled``; everything else (progress, step numbers, log, cancel) stays the
local machinery, because the remote command is streamed through the same ``run_process``.

Safety rules, all pinned by ``tests/test_automix_remote.py``:

* the host is an ssh alias or ``user@host``: never something ssh could read as an option,
  never whitespace;
* every word of the remote command goes through ``shlex.quote`` (``~/`` becomes
  ``"$HOME"/``); the remote paths are built from a per-run unique id;
* ``BatchMode=yes`` (ssh never asks for a password), keep-alives, ``ConnectTimeout``,
  and host key checking is never switched off;
* no password or secret is passed anywhere;
* the remote folder removed afterwards is only ever ``<work_dir>/kuulas-run-<12 hex>``.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import uuid
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from . import toolpath
from .messages import KuulasError, t

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULTS: dict[str, Any] = {
    "enabled": False, "host": "", "cwd": "", "command": ["uv", "run", "automixer"],
    "work_dir": "~/kuulas-remote", "ssh_command": ["ssh"], "rsync_command": ["rsync"],
}
#: ssh options of every call: never prompt, never hang, notice a dead link.
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
               "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
#: Seconds a short remote call (mkdir, rm, pkill, the connection test) may take.
QUICK_SECONDS = 20.0
#: Free space in the work folder below which the test warns.
LOW_DISK_BYTES = 20 * 1024**3
RUN_PREFIX = "kuulas-run-"
_HOST = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.@-]*$")
_SEGMENT = r"[A-Za-z0-9_.+@%=,-]+"
_WORK = re.compile(rf"^(?:~/|/)?{_SEGMENT}(?:/{_SEGMENT})*/?$")
_RUN_DIR = re.compile(rf"/{RUN_PREFIX}[0-9a-f]{{12}}$")
#: rsync / ssh exit codes that mean the link broke (not a full disk or a bad file).
_LINK_CODES = {10, 12, 30, 35, 255}
_PLUGIN_FOLDERS = ("/Library/Audio/Plug-Ins/VST3", "/Library/Audio/Plug-Ins/Components",
                   "/Library/Audio/Plug-Ins/VST", "~/Library/Audio/Plug-Ins/VST3",
                   "~/Library/Audio/Plug-Ins/Components")
_PLUGIN_FORMATS = {".vst3": "VST3", ".component": "AU", ".vst": "VST2"}


class RemoteError(KuulasError, RuntimeError):
    """A bad remote setting or a failed remote step (a message key)."""


def _words(value: Any, default: list[str]) -> list[str]:
    if isinstance(value, list) and value and all(isinstance(x, str) and x for x in value):
        return list(value)
    return list(default)


def resolve(stored: Any) -> dict[str, Any]:
    """The remote settings with defaults filled in (a damaged value falls back)."""
    stored = stored if isinstance(stored, dict) else {}

    def text(key: str) -> str:
        value = stored.get(key)
        return value.strip() if isinstance(value, str) else ""

    return {"enabled": stored.get("enabled") is True, "host": text("host"),
            "cwd": text("cwd"),
            "command": _words(stored.get("command"), DEFAULTS["command"]),
            "work_dir": text("work_dir") or DEFAULTS["work_dir"],
            "ssh_command": _words(stored.get("ssh_command"), DEFAULTS["ssh_command"]),
            "rsync_command": _words(stored.get("rsync_command"),
                                    DEFAULTS["rsync_command"])}


def check_host(host: Any) -> str:
    """``host`` if it is an ssh alias or ``user@host`` that ssh cannot read as an option;
    else ``RemoteError`` (``bad_remote_host``)."""
    if not isinstance(host, str) or not _HOST.match(host):
        raise RemoteError("error.automix.bad_remote_host", host=str(host)[:80])
    return host


def check_work_dir(path: Any) -> str:
    """The work folder if it is a plain path (letters, digits and ``._-+@%=,`` only: it
    is also an rsync argument, which an older rsync splits at spaces)."""
    ok = isinstance(path, str) and _WORK.match(path) and ".." not in path.split("/")
    if not ok:
        raise RemoteError("error.automix.bad_remote_work_dir", path=str(path)[:80])
    return path


def check(remote: dict[str, Any]) -> dict[str, Any]:
    """The settings of an enabled remote, checked; ``RemoteError`` otherwise."""
    check_host(remote["host"])
    check_work_dir(remote["work_dir"])
    return remote


def clean(stored: Any, previous: Any = None) -> dict[str, Any]:
    """The remote settings as saved: checked, only the keys given. ``ssh_command`` and
    ``rsync_command`` (test hooks the dialog does not show) are kept from ``previous``.
    Raises ``RemoteError`` for a wrong shape or a host / folder that is not allowed."""
    if not isinstance(stored, dict):
        raise RemoteError("error.automix.bad_settings")
    out: dict[str, Any] = {}
    for key in ("host", "cwd", "work_dir"):
        value = stored.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            raise RemoteError("error.automix.bad_settings")
        if value.strip():
            out[key] = value.strip()
    for key in ("command", "ssh_command", "rsync_command"):
        value = stored.get(key)
        if value is None:
            continue
        if not _words(value, []) or len(_words(value, [])) != len(value):
            raise RemoteError("error.automix.bad_settings")
        out[key] = value
    if stored.get("enabled") not in (None, True, False):
        raise RemoteError("error.automix.bad_settings")
    out["enabled"] = stored.get("enabled") is True
    if "host" in out:
        check_host(out["host"])
    if "work_dir" in out:
        check_work_dir(out["work_dir"])
    if out["enabled"]:
        check_host(out.get("host", ""))
    prev = previous if isinstance(previous, dict) else {}
    for key in ("ssh_command", "rsync_command"):
        if key not in out and key in prev:
            out[key] = prev[key]
    return out


# -- quoting and argument lists ----------------------------------------------------------


def word(w: str) -> str:
    """One word for the remote shell: quoted; a leading ``~/`` is the remote home."""
    if w == "~":
        return '"$HOME"'
    if w.startswith("~/") and len(w) > 2:
        return '"$HOME"/' + shlex.quote(w[2:])
    return shlex.quote(w)


def line(words: list[str]) -> str:
    """The remote shell command for ``words``."""
    return " ".join(word(w) for w in words)


def ssh_argv(remote: dict[str, Any], shell_command: str) -> list[str]:
    """``ssh`` for ``host`` running ``shell_command`` (one argument, the last)."""
    return [*remote["ssh_command"], *SSH_OPTIONS, "--", remote["host"], shell_command]


def command_line(remote: dict[str, Any], words: list[str]) -> str:
    """``cd <cwd> && <words>``: how the automixer is started in its folder."""
    run = line(words)
    return f"cd {word(remote['cwd'])} && {run}" if remote["cwd"] else run


def runner(remote: dict[str, Any], base: Callable) -> Callable:
    """A ``RunProcess`` that runs the given command words on the remote Mac in its
    folder: ``automix.run_process`` (or a test's fake) is given the ssh argument list.
    Output, exit code and cancel behave as for a local run."""
    def run(cmd, _cwd, on_line, cancel) -> int:
        return base(ssh_argv(remote, command_line(remote, list(cmd))), None, on_line,
                    cancel)
    return run


def new_run_dir(remote: dict[str, Any]) -> str:
    """A path that has never been used: ``<work_dir>/kuulas-run-<12 hex>``."""
    base = check_work_dir(remote["work_dir"]).rstrip("/")
    return f"{base}/{RUN_PREFIX}{uuid.uuid4().hex[:12]}"


def quick(remote: dict[str, Any], shell_command: str,
          timeout: float = QUICK_SECONDS) -> tuple[int | None, str]:
    """Run a short remote command and wait: ``(exit code, output)``; ``(None, why)`` when
    ssh could not be started or timed out. Never raises."""
    try:
        done = subprocess.run(  # noqa: S603 - an argument list, no local shell
            ssh_argv(remote, shell_command), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            errors="replace", timeout=timeout, check=False, env=toolpath.tool_env())
    except subprocess.TimeoutExpired:
        return None, "timed out"
    except OSError as e:
        return None, str(e)
    return done.returncode, done.stdout.strip()


def kill_remote(remote: dict[str, Any], run_dir: str) -> None:
    """Best effort: end an automixer still running in ``run_dir`` (ssh may leave it).
    ``[k]`` in the pattern keeps pkill from matching the shell that runs it."""
    name = PurePosixPath(run_dir).name
    if not name.startswith(RUN_PREFIX):
        return
    quick(remote, line(["pkill", "-f", f"[{name[0]}]{name[1:]}"]))


def remove_remote(remote: dict[str, Any], run_dir: str) -> bool:
    """Best effort: remove the run's folder on the remote Mac. Only ever a path ending in
    ``/kuulas-run-<12 hex>``; an empty path or ``/`` is refused (False)."""
    if not run_dir or run_dir.strip("/") == "" or not _RUN_DIR.search(run_dir):
        return False
    code, _ = quick(remote, line(["rm", "-rf", "--", run_dir]))
    return code == 0


def rsync_argv(remote: dict[str, Any], source: str, target: str,
               extra: list[str] | None = None) -> list[str]:
    """``rsync -a --partial -v`` over the same ssh options; ``source`` / ``target`` may be
    ``host:path``. Files are named one per output line (``-v``) for the progress."""
    shell = " ".join(shlex.quote(x) for x in [*remote["ssh_command"], *SSH_OPTIONS])
    return [*remote["rsync_command"], "-a", "--partial", "-v", "-e", shell,
            *(extra or []), source, target]


def at(remote: dict[str, Any], path: str) -> str:
    """``host:path`` for rsync."""
    return f"{remote['host']}:{path}"


def transfer_error(host: str, code: int, lines) -> RemoteError:
    """The error for a failed rsync: a broken link or another failure."""
    key = "error.automix.remote_lost" if code in _LINK_CODES else (
        "error.automix.remote_transfer")
    return RemoteError(key, host=host, code=code, tail="\n".join(list(lines)[-15:]))


# -- the connection test -----------------------------------------------------------------


def _check(name: str, ok: bool, detail: str = "", *, warn: bool = False) -> dict:
    return {"id": name, "ok": ok, "warn": warn and ok, "detail": detail}


def _last(text: str) -> str:
    rows = [r for r in text.splitlines() if r.strip()]
    return rows[-1][:200] if rows else ""


def connection_test(stored: Any, gated: dict[str, str]) -> dict[str, Any]:
    """Check the remote settings one thing at a time: ``{"ok", "checks": [{"id", "ok",
    "warn", "detail"}]}``. ``gated`` is ``{option key: flag}`` to look for in the remote
    automixer's ``--help``. Nothing here may hang (ssh ``ConnectTimeout``, a timeout on
    every call) or prompt for a password (``BatchMode``)."""
    remote = resolve(stored)
    checks: list[dict] = []
    try:
        check(remote)
    except RemoteError as e:
        return {"ok": False, "checks": [_check("settings", False, t(e.key, **e.params))]}
    local = toolpath.resolve(remote["rsync_command"][0])
    checks.append(_check("rsync_local", local is not None,
                         "" if local else remote["rsync_command"][0]))
    code, out = quick(remote, "echo kuulas-ok")
    reached = code == 0 and "kuulas-ok" in out
    checks.append(_check("ssh", reached, "" if reached else _last(out)))
    if reached:
        checks += _remote_checks(remote, gated)
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def _remote_checks(remote: dict[str, Any], gated: dict[str, str]) -> list[dict]:
    checks: list[dict] = []
    have_rsync, _ = quick(remote, "command -v rsync")
    checks.append(_check("rsync_remote", have_rsync == 0))
    work = word(check_work_dir(remote["work_dir"]))
    code, out = quick(remote, f"mkdir -p {work} && df -Pk {work}")
    free = _free_bytes(out) if code == 0 else None
    if free is None:
        checks.append(_check("disk", False, _last(out)))
    else:
        gb = free / 1024**3
        checks.append(_check("disk", True, f"{gb:.0f} GB", warn=free < LOW_DISK_BYTES))
    if remote["cwd"]:
        code, out = quick(remote, line(["test", "-d", remote["cwd"]]))
        folder_ok = code == 0
    else:
        folder_ok = True
    checks.append(_check("cwd", folder_ok, "" if folder_ok else remote["cwd"]))
    if not folder_ok:
        return checks
    code, out = quick(remote, command_line(remote, [*remote["command"], "--help"]),
                      timeout=60.0)
    answered = code == 0
    checks.append(_check("command", answered, "" if answered else _last(out)))
    if answered:
        found = [key for key, flag in gated.items() if flag in out]
        missing = [key for key in gated if key not in found]
        checks.append(_check("flags", not missing,
                             ", ".join(gated[k] for k in found), warn=False)
                      | {"missing": [gated[k] for k in missing]})
    return checks


def _free_bytes(df_output: str) -> int | None:
    rows = df_output.strip().splitlines()
    try:
        return int(rows[-1].split()[3]) * 1024
    except (IndexError, ValueError):
        return None


# -- the remote Mac's plug-ins -----------------------------------------------------------


def list_plugins(stored: Any) -> list[dict] | None:
    """The plug-ins installed on the remote Mac as ``{"name", "format", "path"}`` (paths
    as it sees them), found by an ssh ``find`` in the standard folders (names only,
    nothing is loaded). None when ssh fails (the dialog then offers a text field)."""
    remote = check(resolve(stored))
    folders = " ".join(word(p) if p.startswith("~/") else shlex.quote(p)
                       for p in _PLUGIN_FOLDERS)
    shell = (f"find {folders} -maxdepth 3 \\( -name '*.vst3' -o -name '*.component' "
             "-o -name '*.vst' \\) -prune -print 2>/dev/null; true")
    code, out = quick(remote, shell)
    if code != 0:  # the command ends in ``true``: only ssh itself can fail
        return None
    found: dict[str, dict] = {}
    for row in out.splitlines():
        path = PurePosixPath(row.strip())
        kind = _PLUGIN_FORMATS.get(path.suffix.lower())
        if not row.startswith("/") or kind is None:
            continue
        found.setdefault(str(path), {"name": path.stem, "format": kind,
                                     "path": str(path)})
    return sorted(found.values(), key=lambda p: (p["name"].lower(), p["path"]))
