"""The log level: ``KUULAS_LOG_LEVEL`` (DEBUG, INFO or WARNING), else the per-user
``log_level`` in settings.json (Help > Log level), else INFO.

The app bundle has no terminal; its log file is all a tester can send, so the level must
be changeable without a developer's tools. The environment wins over the setting so a
one-off run (``KUULAS_LOG_LEVEL=DEBUG kuulas open ...``) needs no settings change.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from . import messages

LEVELS = ("DEBUG", "INFO", "WARNING")
DEFAULT = "INFO"
ENV = "KUULAS_LOG_LEVEL"


def parse(value: object) -> str | None:
    """The level ``value`` names (any case), or None when it is not one of ``LEVELS``."""
    text = value.strip().upper() if isinstance(value, str) else ""
    return text if text in LEVELS else None


def level_setting() -> str | None:
    """The saved level, or None (no file, damaged file, unknown value)."""
    try:
        data = json.loads(messages.settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return parse(data.get("log_level")) if isinstance(data, dict) else None


def save_level_setting(value: str) -> None:
    """Remember the level for this user. ``ValueError`` for a level we do not offer;
    ``OSError`` if the file cannot be written."""
    level = parse(value)
    if level is None:
        raise ValueError(value)
    path = messages.settings_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["log_level"] = level
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve(env: Mapping[str, str], setting: str | None) -> str:
    """Environment, then setting, then INFO; an unknown value falls through."""
    return parse(env.get(ENV, "")) or parse(setting) or DEFAULT


def source(env: Mapping[str, str], setting: str | None) -> str:
    """Where ``resolve`` got its answer: ``env``, ``setting`` or ``default``."""
    if parse(env.get(ENV, "")):
        return "env"
    return "setting" if parse(setting) else "default"


def apply(level: str, *, console: bool = False) -> None:
    """Set the root logger's level now. ``console``: also log to stderr when nothing
    is attached yet (``kuulas open`` in a terminal; the bundle has its file handler)."""
    root = logging.getLogger()
    if console and not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(getattr(logging, level))


def current() -> str:
    """The root logger's level as one of ``LEVELS`` (anything else shows as INFO)."""
    name = logging.getLevelName(logging.getLogger().level)
    return name if name in LEVELS else DEFAULT
