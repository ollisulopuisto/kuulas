"""Authenticated command-line client for an already-running Kuulas project."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import ctl_discovery
from .messages import KuulasError


class CtlError(KuulasError):
    """A localized failure while addressing a running local project."""


def call_server(port: int, token: str, path: str, method: str = "GET",
                body: dict[str, Any] | None = None, *,
                timeout: float = 10.0) -> Any:
    """Make one loopback API request with the running window's capability token."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method,
        headers={"Accept": "application/json", "X-Kuulas-Token": token,
                 **({"Content-Type": "application/json"} if data is not None else {})},
    )
    try:
        # The URL is fixed to loopback above; no caller controls its scheme/host.
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read())
            detail = payload.get("error", {}).get("text", str(error))
        except (ValueError, AttributeError):
            detail = str(error)
        raise CtlError("error.ctl.request_failed", detail=detail) from error
    except (OSError, TimeoutError) as error:
        raise CtlError("error.ctl.unreachable", detail=str(error)) from error
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError as error:
        raise CtlError("error.ctl.invalid_response") from error


_ROUTES = {
    "ping": ("GET", "/api/state"),
    "state": ("GET", "/api/state"),
    "words": ("GET", "/api/words"),
    "commands": ("GET", "/api/commands"),
    "stats": ("GET", "/api/stats"),
    "undo": ("POST", "/api/undo"),
    "redo": ("POST", "/api/redo"),
    "transport": ("GET", "/api/transport"),
}


def run_ctl(project: str | Path, command: str,
            args: dict[str, Any] | None = None) -> Any:
    """Route a read or catalogued command to the project's running window."""
    folder = Path(project).expanduser().resolve()
    info = ctl_discovery.read(folder)
    if info is None:
        raise CtlError("error.ctl.not_running", path=str(folder))
    if not ctl_discovery.is_alive(info):
        ctl_discovery.remove(folder)
        raise CtlError("error.ctl.process_dead", path=str(folder))

    if command in _ROUTES:
        method, route = _ROUTES[command]
        if command == "transport" and args:
            return call_server(info["port"], info["token"], route, "POST", args)
        return call_server(info["port"], info["token"], route, method,
                           {} if method == "POST" else None)

    catalog = call_server(info["port"], info["token"], "/api/commands")
    entry = next((item for item in catalog.get("commands", [])
                  if item.get("name") == command), None)
    if entry is None:
        raise CtlError("error.ctl.unknown_command", name=command)
    path = entry["via"]
    key = "op" if path == "/api/edit" else "name"
    payload = {key: command, "args": args or {}}
    return call_server(info["port"], info["token"], path, "POST", payload)
