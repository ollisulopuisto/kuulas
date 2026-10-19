"""User-facing messages: catalogs in English and Finnish, and a ``t`` that never raises.

English is the source. Every message is a key in ``locales/en.json`` and
``locales/fi.json``, with ``{name}`` placeholders. Messages are made on error
paths, so a bad key or a missing value must come out as readable text, never
as a second exception that hides the first one.

speechmix's messages go through the same catalogs: kuulas registers as its
translator, so pipeline errors are in Finnish too.
"""

from __future__ import annotations

import json
import locale
import os
import re
import string
import subprocess
import sys
from pathlib import Path
from typing import Any

import speechmix

SOURCE = "en"
LANGUAGES = ("en", "fi")
_LOCALES = Path(__file__).resolve().parent / "locales"


def _load(lang: str) -> dict[str, Any]:
    return json.loads((_LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


_CATALOGS: dict[str, dict[str, Any]] = {lang: _load(lang) for lang in LANGUAGES}


def _normalise(lang: str) -> str:
    """'fi_FI.UTF-8' and 'fi-FI' become 'fi'; anything we do not ship is English."""
    code = lang.strip().lower().replace("_", "-").split("-")[0].split(".")[0]
    return code if code in LANGUAGES else SOURCE


def _apple_languages() -> list[str]:
    """macOS's language list, most wanted first; empty anywhere else or on failure.

    A Terminal on a Finnish Mac usually still has ``LANG=en_US.UTF-8``, so
    LANG alone says English. ``defaults`` is the system's real answer.
    """
    if sys.platform != "darwin":
        return []
    try:
        done = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],  # noqa: S607 - macOS tool
            capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        # No such tool, or it hung: LANG will have to do.
        return []
    if done.returncode != 0:
        return []
    return re.findall(r'[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*', done.stdout)


AUTO = "auto"


def settings_file() -> Path:
    """The per-user app settings: ``$KUULAS_SETTINGS_FILE`` (tests, portable
    setups) or ``settings.json`` in the per-user config folder."""
    override = os.environ.get("KUULAS_SETTINGS_FILE")
    if override:
        return Path(override)
    from .desktop import config_dir  # noqa: PLC0415 - desktop imports this module
    return config_dir() / "settings.json"


def language_setting() -> str:
    """View > Language: ``"auto"`` (follow the system), ``"en"`` or ``"fi"``.
    A missing or damaged file, or a language we do not ship, means ``"auto"``."""
    try:
        data = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AUTO
    value = data.get("language") if isinstance(data, dict) else None
    return value if value in LANGUAGES else AUTO


def save_language_setting(value: str) -> None:
    """Remember the choice for this user. ``ValueError`` for anything but
    ``"auto"`` or a shipped language; ``OSError`` if the file cannot be written."""
    if value != AUTO and value not in LANGUAGES:
        raise ValueError(value)
    path = settings_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["language"] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def default_language() -> str:
    """The language the OS asks for.

    Order: LC_ALL and LC_MESSAGES (an explicit override), the app's own
    language setting (View > Language), the macOS language
    list, LANG, then the locale. The first language kuulas ships wins on the
    macOS list; one we do not ship is skipped, as the system itself does.
    """
    for var in ("LC_ALL", "LC_MESSAGES"):
        value = os.environ.get(var, "")
        if value:
            return _normalise(value)
    chosen = language_setting()
    if chosen != AUTO:
        return chosen
    apple = _apple_languages()
    for tag in apple:
        primary = _normalise(tag)
        if primary != SOURCE or tag.lower().startswith("en"):
            return primary
    if apple:
        return SOURCE
    value = os.environ.get("LANG", "")
    if value:
        return _normalise(value)
    try:
        value = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        # An unknown locale name in the environment is not a reason to fail.
        value = ""
    return _normalise(value) if value else SOURCE


_language = None


def set_language(lang: str) -> None:
    """Choose the language for every message made from now on."""
    global _language  # noqa: PLW0603 - process-wide, as gettext's is
    _language = _normalise(lang)


def catalog(lang: str) -> dict[str, Any] | None:
    """The whole catalog of a shipped language, for the UI; None for any other."""
    return _CATALOGS.get(lang)


def language() -> str:
    global _language  # noqa: PLW0602
    if _language is None:
        _language = default_language()
    return _language


def _template(lang: str, key: str, count: Any) -> str | None:
    entry = _CATALOGS[lang].get(key)
    if isinstance(entry, dict):
        # CLDR for both languages we ship: "one" is exactly 1, "other" is the rest.
        category = "one" if count == 1 else "other"
        return entry.get(category, entry.get("other"))
    return entry


class _Filler(string.Formatter):
    """Fills placeholders; a missing value is left as ``{name}`` instead of raising."""

    def get_value(self, key, _args, kwargs):
        if isinstance(key, int):
            return _Missing("{}")
        if key in kwargs:
            return kwargs[key]
        return _Missing("{" + key + "}")

    def format_field(self, value, format_spec):
        if isinstance(value, _Missing):
            return str(value)
        return super().format_field(value, format_spec)


class _Missing(str):
    """A placeholder with no value: shown as written, never formatted."""


def _bare(key: str, values: dict[str, Any]) -> str:
    """The key itself, with the values, when no template can be used."""
    extra = ", ".join(f"{name}={value}" for name, value in values.items())
    return f"{key} ({extra})" if extra else key


def t(key: str, /, **values: Any) -> str:
    """The message for ``key`` in the current language. Never raises.

    Order: the current language, then English, then the key itself. A
    ``count`` value picks the plural category of an entry that has one.
    """
    lang = language()
    template = _template(lang, key, values.get("count"))
    if template is None and lang != SOURCE:
        template = _template(SOURCE, key, values.get("count"))
    if template is None:
        return _bare(key, values)
    try:
        return _Filler().vformat(template, (), values)
    except (ValueError, IndexError, KeyError, TypeError, AttributeError):
        # A format spec the value cannot take, or an attribute of a missing value.
        return _bare(key, values)


def _jsonable(params: dict[str, Any]) -> dict[str, Any]:
    return {
        name: value if value is None or isinstance(value, (str, int, float, bool))
        else str(value)
        for name, value in params.items()
    }


def error_body(key: str, /, **params: Any) -> dict[str, Any]:
    """The API's error shape: ``{"error": {"key", "params", "text"}}``.

    ``text`` is in the session's language, so the UI can show it without a
    catalog of its own for server errors.
    """
    return {"error": {"key": key, "params": _jsonable(params), "text": t(key, **params)}}


class KuulasError(Exception):
    """An error whose message is a catalog key and its values.

    ``str()`` translates at the moment it is read, so a message made in one
    language follows the setting if it is shown after a change.
    """

    def __init__(self, key: str, /, **params: Any) -> None:
        super().__init__(key)
        self.key = key
        self.params = params

    def __str__(self) -> str:
        return t(self.key, **self.params)


def _speechmix_translate(key: str, /, **values: Any) -> str:
    """speechmix's translator. Raises for a key we do not know, so speechmix
    uses its own English text instead of showing a bare key.
    """
    if key not in _CATALOGS[SOURCE]:
        raise KeyError(key)
    return t(key, **values)


speechmix.set_translator(_speechmix_translate)
