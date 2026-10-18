"""Discovery file for a running kuulas window.

A running kuulas window publishes where it listens so that ``kuulas ctl`` can
find it. This module is standalone: it uses only the Python standard library.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REQUIRED_FIELDS = ("port", "token", "pid", "started_utc")


def discovery_path(project_folder: str | os.PathLike[str]) -> Path:
    """Return the path to the discovery file inside ``project_folder``."""
    return Path(project_folder) / "ctl.json"


def new_token() -> str:
    """Return a URL-safe random token with at least 32 bytes of entropy."""
    return secrets.token_urlsafe(32)


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write(
    project_folder: str | os.PathLike[str],
    port: int,
    token: str,
    pid: int,
) -> None:
    """Write the discovery file atomically with mode ``0600``.

    The file is created via a temporary file in the same folder and then
    renamed with ``os.replace`` so readers never see a partial file.
    """
    path = discovery_path(project_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "port": port,
        "token": token,
        "pid": pid,
        "started_utc": _utc_now(),
    }
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    temp = path.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    written = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            written = True
    finally:
        if not written:
            temp.unlink(missing_ok=True)
    os.replace(temp, path)


def _valid_info(value: Any) -> dict[str, Any] | None:
    """Return ``value`` if it is a valid discovery dict, else ``None``."""
    if not isinstance(value, dict):
        return None
    checks = (
        all(field in value for field in _REQUIRED_FIELDS),
        isinstance(value.get("port"), int) and not isinstance(value.get("port"), bool),
        isinstance(value.get("token"), str),
        isinstance(value.get("pid"), int) and not isinstance(value.get("pid"), bool),
        isinstance(value.get("started_utc"), str),
    )
    return value if all(checks) else None


def read(project_folder: str | os.PathLike[str]) -> dict[str, Any] | None:
    """Read and validate the discovery file, returning ``None`` on any error."""
    path = discovery_path(project_folder)
    try:
        data = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return None
    return _valid_info(value)


def is_alive(info: dict[str, Any]) -> bool:
    """Return whether ``info["pid"]`` refers to a running process."""
    pid = info.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False
    return True


def remove(project_folder: str | os.PathLike[str]) -> None:
    """Delete the discovery file, ignoring a missing file."""
    discovery_path(project_folder).unlink(missing_ok=True)


def check_token(info: dict[str, Any], given: Any) -> bool:
    """Compare ``given`` with ``info["token"]`` using a timing-safe comparison."""
    token = info.get("token")
    if not isinstance(token, str) or not isinstance(given, str):
        return False
    return hmac.compare_digest(token, given)
