"""The UI's remembered settings (theme, density, fast-listening speed, ...), kept in
one JSON file in the user's config folder, beside ``settings.json``.

Browser storage cannot hold them: the desktop app serves every window on a fresh
random port (a new origin, so empty storage) and the webview runs private. The file
is ``{key: string}``; keys are ``kuulas.*`` or short plain names, values strings of
bounded length, the whole file is size-capped. It holds preferences only, never
secrets. A missing or damaged file means "nothing remembered", never an error.
Windows of different projects share it; the last write wins per key.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from pathlib import Path

from .messages import config_dir

MAX_BYTES = 256 * 1024
MAX_KEY = 120
MAX_VALUE = 16 * 1024
_KEY = re.compile(r"^(kuulas\.[A-Za-z0-9_.:-]+|[A-Za-z0-9_-]{1,32})$")
_LOCK = threading.Lock()


class PrefsError(ValueError):
    """The request is not an acceptable change to the stored preferences."""


def prefs_path() -> Path:
    """``$KUULAS_UI_PREFS_FILE`` (tests) or ``ui-prefs.json`` in the config folder."""
    override = os.environ.get("KUULAS_UI_PREFS_FILE")
    return Path(override) if override else config_dir() / "ui-prefs.json"


def _key_ok(key: object) -> bool:
    return isinstance(key, str) and len(key) <= MAX_KEY and _KEY.match(key) is not None


def _read() -> dict[str, str]:
    try:
        data = json.loads(prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items()
            if _key_ok(k) and isinstance(v, str) and len(v) <= MAX_VALUE}


def load() -> dict[str, str]:
    with _LOCK:
        return _read()


def update(set_: object = None, remove: object = None) -> dict[str, str]:
    """Apply ``set_`` ({key: str}) then ``remove`` ([key]); returns the stored result.
    Raises ``PrefsError`` (nothing written) for a bad key or value, or a file too big."""
    set_ = {} if set_ is None else set_
    remove = [] if remove is None else remove
    if not isinstance(set_, dict) or not isinstance(remove, list):
        raise PrefsError("set must be an object and remove a list")
    for key, value in set_.items():
        if not _key_ok(key) or not isinstance(value, str) or len(value) > MAX_VALUE:
            raise PrefsError(f"bad preference {str(key)[:40]!r}")
    if not all(_key_ok(k) for k in remove):
        raise PrefsError("bad key in remove")
    with _LOCK:
        data = _read()
        data.update(set_)
        for key in remove:
            data.pop(key, None)
        text = json.dumps(data, indent=1, sort_keys=True)
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise PrefsError("preferences file would be too large")
        path = prefs_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ui-prefs-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, path)
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return data
