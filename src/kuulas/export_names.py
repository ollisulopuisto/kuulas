"""What exported files are called: the project first, the edit only when it matters.

Every export of the main edit used to be called "Pääeditio ..." because the
edit's name led the file name and the project's did not (owner, 2026-10-20).
Now a file leads with the project name (``title``), and the edit's name follows
only when the file is not of the main edit, so another edit's export neither
overwrites nor looks like the main one. Pure string logic, no I/O.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from . import messages
from .history import MAIN_EDIT

#: The shipped languages. A project made in one and opened in the other still
#: holds the first one's name for its main edit.
_LOCALES = ("en", "fi")

#: The built-in templates before this change, and what replaced them. Only an
#: exact match is migrated: a remembered template the user wrote stays as typed.
OLD_DEFAULTS = {
    "{edit} v{n}.{ext}": "{title} v{n}.{ext}",
    "{edit} {from}\N{EN DASH}{to} v{n}.{ext}": "{title} {from}\N{EN DASH}{to} v{n}.{ext}",
    "{edit}{span} tracks v{n}": "{title}{span} tracks v{n}",
    "{edit} {stamp} v{n}": "{title} {stamp} v{n}",
    "{edit} {stamp} v{n}.{ext}": "{title} {stamp} v{n}.{ext}",
}


def default_edit_names() -> set[str]:
    """The main edit's default name in every shipped language."""
    return {(messages.catalog(lang) or {}).get("history.main_edit", "")
            for lang in _LOCALES} - {""}


def is_main_edit(edit_id: str, edit_name: str) -> bool:
    """The main edit: its id is the stored flag; the default name, in any
    language, marks it too (a copy that kept the name is not worth a suffix)."""
    return edit_id == MAIN_EDIT or edit_name in default_edit_names()


def title(project: str, edit_id: str, edit_name: str) -> str:
    """``<project>`` for the main edit, ``<project> - <edit>`` for another."""
    if is_main_edit(edit_id, edit_name):
        return project
    return f"{project} - {edit_name}"


def stamp(when: datetime) -> str:
    """Local time as the takes' file names have it: ``2026-10-20 15-33-43``."""
    return when.strftime("%Y-%m-%d %H-%M-%S")


def migrate_template(template: str) -> str:
    """A remembered built-in default becomes the new one; anything else is kept."""
    return OLD_DEFAULTS.get(template, template)


def disposition(name: str) -> str:
    """A Content-Disposition for a download: an ASCII fallback plus the real
    UTF-8 name (RFC 5987), since project names have ä and ö."""
    plain = name.encode("ascii", "replace").decode()
    plain = plain.replace("?", "_").replace('"', "_").replace("\\", "_")
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name)}"
