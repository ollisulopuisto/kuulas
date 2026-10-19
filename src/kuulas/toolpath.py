"""Finding outside programs (``uvx``, ``colab-transcribe``, ``ffmpeg``).

An app started from Finder gets ``PATH=/usr/bin:/bin:/usr/sbin:/sbin``: no Homebrew, no
``~/.local/bin`` (where ``uv tool install`` puts things), no ``~/.cargo/bin``. A program
that works in Terminal is then "not found". So every program kuulas starts for the user
(Colab, the automixer) is looked up on the given ``PATH`` first and then in the usual
install folders, and started with that wider ``PATH`` so what it starts itself is found
too. Pure functions: the environment and home folder are arguments.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path


def extra_dirs(home: Path) -> list[str]:
    """The folders programs are usually installed in, besides ``PATH``."""
    return [
        "/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin",
        str(home / ".local" / "bin"), str(home / ".cargo" / "bin"),
        str(home / ".local" / "share" / "uv" / "tools" / "google-colab-cli" / "bin"),
    ]


def search_path(env: Mapping[str, str], home: Path | None = None) -> str:
    """``env['PATH']`` followed by the usual install folders, without repeats."""
    home = home if home is not None else Path.home()
    given = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    seen: list[str] = []
    for entry in [*given, *extra_dirs(home)]:
        if entry not in seen:
            seen.append(entry)
    return os.pathsep.join(seen)


def resolve(program: str, env: Mapping[str, str] | None = None,
            home: Path | None = None) -> str | None:
    """The absolute path of ``program`` or None. A name with a slash is taken as it is
    (when it is an executable file); a bare name is searched on :func:`search_path`."""
    env = os.environ if env is None else env
    if os.sep in program:
        path = Path(program).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(program, path=search_path(env, home))


def tool_env(env: Mapping[str, str] | None = None,
             home: Path | None = None) -> dict[str, str]:
    """The environment for a program kuulas starts: ``env`` with the wider ``PATH`` and
    without ``VIRTUAL_ENV`` (which belongs to kuulas's own environment and makes
    ``uv run`` in another checkout warn that it will be ignored)."""
    env = os.environ if env is None else env
    out = {k: v for k, v in env.items() if k != "VIRTUAL_ENV"}
    out["PATH"] = search_path(env, home)
    return out
