"""Remote control client for a running kuulas window or server (WP52).

Discovers the port and authentication token via ``ctl_discovery`` and dispatches
edits, commands, transport actions, and queries to the live instance.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from . import ctl_discovery
from .messages import KuulasError


class CtlError(KuulasError):
    """An error running a ctl command."""


def call_server(
    port: int,
    token: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Perform an HTTP request to the running kuulas server."""
    url = f"http://127.0.0.1:{port}{path}"
    headers = {
        "Accept": "application/json",
        "X-Kuulas-Token": token,
    }
    data = None
    if body is not None or method in ("POST", "PUT"):
        data = json.dumps(body or {}).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=data, headers=headers, method=method)  # noqa: S310
    try:
        with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            content = resp.read()
            if not content:
                return {}
            return json.loads(content.decode("utf-8"))
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = {"error": raw}
        msg = parsed.get("error") or parsed.get("detail") or str(e)
        raise CtlError("error.ctl.http_error", status=e.code, message=str(msg)) from e
    except error.URLError as e:
        raise CtlError("error.ctl.connection_failed", error=str(e.reason)) from e
    except OSError as e:
        raise CtlError("error.ctl.failed", error=str(e)) from e


def get_discovery(project_folder: str | os.PathLike[str]) -> dict[str, Any]:
    """Read discovery file and ensure process is alive."""
    info = ctl_discovery.read(project_folder)
    if info is None:
        raise CtlError("error.ctl.not_running", path=str(project_folder))
    if not ctl_discovery.is_alive(info):
        ctl_discovery.remove(project_folder)
        raise CtlError("error.ctl.process_dead", pid=info.get("pid"))
    return info


_QUERY_ROUTES = {
    "ping": ("/api/state", "GET"),
    "state": ("/api/state", "GET"),
    "words": ("/api/words", "GET"),
    "commands": ("/api/commands", "GET"),
    "stats": ("/api/stats", "GET"),
    "undo": ("/api/undo", "POST"),
    "redo": ("/api/redo", "POST"),
}


def run_ctl(
    project_folder: str | os.PathLike[str],
    command: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a ctl command against a running kuulas instance.

    Supported commands:
    - ``state``: returns GET /api/state
    - ``words``: returns GET /api/words
    - ``commands``: returns GET /api/commands
    - ``stats``: returns GET /api/stats
    - ``undo``: calls POST /api/undo
    - ``redo``: calls POST /api/redo
    - ``ping``: checks if server responds
    - ``transport``: sends action to POST /api/transport (play, stop, seek, etc.)
    - Any command listed in ``command_catalog``: routed to /api/edit or /api/command.
    """
    info = get_discovery(project_folder)
    port = info["port"]
    token = info["token"]
    args = args or {}
    cmd = command.lower()

    if cmd in _QUERY_ROUTES:
        path, method = _QUERY_ROUTES[cmd]
        return call_server(port, token, path, method=method)

    if cmd == "transport":
        return call_server(port, token, "/api/transport", method="POST", body=args)

    # Resolve command via command catalogue
    cat = call_server(port, token, "/api/commands")
    matching = [e for e in cat.get("commands", []) if e.get("name") == command]
    if not matching:
        raise CtlError("error.ctl.unknown_command", command=command)

    entry = matching[0]
    via = entry.get("via", "/api/edit")
    if via in ("/api/edit", "/api/command"):
        key = "op" if via == "/api/edit" else "name"
        payload = {key: command, "args": args}
        return call_server(port, token, via, method="POST", body=payload)

    raise CtlError("error.ctl.unsupported_via", via=via)
