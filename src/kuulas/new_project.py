"""File > New project... and Open project... (WP74), the parts that need no window.

In the desktop window the native dialogs (``desktop.Bridge``) name the folder and a
window opens it. In a plain browser there is no such dialog: the page asks for a name and
a folder, the server makes the project and starts ``kuulas open`` on it (a new tab).

The name rules, because the name becomes a folder name on the user's disk: not empty, at
most 100 characters, no path separator or NUL, not ``.`` / ``..`` and not hidden (a
leading dot); the ``.kuulas`` suffix is added once (typed in any case, kept lower case).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .ops import EditError

SUFFIX = ".kuulas"
MAX_NAME = 100
_FORBIDDEN = "/\\\0<>:\"|?*"


def folder_name(typed: object) -> str:
    """The project folder name for what the user typed (``EditError``
    ``error.project.bad_name`` when it cannot be one)."""
    text = typed.strip() if isinstance(typed, str) else ""
    if text.lower().endswith(SUFFIX):
        text = text[: -len(SUFFIX)].rstrip()
    if (not text or len(text) > MAX_NAME or text.startswith(".")
            or any(char in text for char in _FORBIDDEN)
            or any(ord(char) < 32 or ord(char) == 127 for char in text)):
        raise EditError("error.project.bad_name")
    return text + SUFFIX


def project_path(parent: object, name: object) -> Path:
    """``parent``/``name``.kuulas for a new project: ``parent`` is an absolute path to
    an existing folder without ``..`` (``error.project.bad_parent``), and nothing is
    there yet (``error.project.exists``). Nothing is created."""
    folder = folder_name(name)
    if not isinstance(parent, str) or not parent.strip() or "\0" in parent:
        raise EditError("error.project.bad_parent", path=str(parent)[:200])
    raw_parent = Path(parent)
    if not raw_parent.is_absolute() or ".." in raw_parent.parts:
        raise EditError("error.project.bad_parent", path=parent[:200])
    norm_parent = os.path.normpath(parent)
    if not os.path.isabs(norm_parent) or not os.path.isdir(norm_parent):
        raise EditError("error.project.bad_parent", path=parent[:200])
    real_parent = os.path.realpath(norm_parent)
    target_str = os.path.normpath(os.path.join(real_parent, folder))
    if not target_str.startswith(real_parent + os.sep):
        raise EditError("error.project.bad_name")
    target = Path(target_str)
    if target.exists() or target.is_symlink():
        raise EditError("error.project.exists", path=str(target))
    return target


def create(parent: object, name: object) -> Path:
    """Make the empty project and return its folder."""
    # Imported here: the session pulls in the audio libraries.
    from .session import Session  # noqa: PLC0415

    target = project_path(parent, name)
    Session(target).close()
    return target


def window_command(folder: str, executable: str | None = None) -> list[str]:
    """The command that serves ``folder`` and opens it in a new browser tab."""
    return [executable or sys.executable, "-m", "kuulas", "open", folder]


def checked_project_folder(folder: object) -> str:
    """The absolute path of an existing ``*.kuulas`` folder, or ``EditError``
    (``error.project.bad_parent``). The folder comes from the browser's request, so it is
    checked before it goes on a command line: no option-like text, no NUL, absolute,
    real."""
    if (not isinstance(folder, str) or not folder or "\0" in folder
            or folder.startswith("-")):
        raise EditError("error.project.bad_parent", path=str(folder)[:200])
    raw_path = Path(folder)
    if not raw_path.is_absolute() or raw_path.suffix != SUFFIX or ".." in raw_path.parts:
        raise EditError("error.project.bad_parent", path=folder[:200])
    norm = os.path.normpath(folder)
    real = os.path.realpath(norm)
    if not os.path.isdir(real):
        raise EditError("error.project.bad_parent", path=folder[:200])
    return real


def start_window(folder: str) -> None:
    """Start a second kuulas on ``folder`` beside this one, not waiting for it.

    The folder becomes the child's working directory and the command opens ``.``, so
    the request's text never reaches the command line (CodeQL py/command-line-injection,
    66). ``open_project`` makes ``.`` absolute before anything keys on it."""
    safe = checked_project_folder(folder)
    subprocess.Popen(  # noqa: S603 - our own interpreter and a constant argument; the folder is cwd
        window_command("."), cwd=safe, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
