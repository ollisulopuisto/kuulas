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
import string
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


def default_language() -> str:
    """The language the OS asks for: LC_ALL, LC_MESSAGES, LANG, then the locale."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value:
            return _normalise(value)
    try:
        value = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        # An unknown locale name in the environment is not a reason to fail.
        value = ""
    return _normalise(value) if value else SOURCE


_language = default_language()


def set_language(lang: str) -> None:
    """Choose the language for every message made from now on."""
    global _language  # noqa: PLW0603 - process-wide, as gettext's is
    _language = _normalise(lang)


def language() -> str:
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
    template = _template(_language, key, values.get("count"))
    if template is None and _language != SOURCE:
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
