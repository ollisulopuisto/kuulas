"""Which build is running: the version plus the commit, for bug reports.

The owner tests on one computer while the code is edited on another, so
"v26.10.18.64" alone does not say which commits are in the build (the version
moves only in a docs commit). The label adds the short commit (and "+dirty" for
uncommitted changes) when the code runs from a git checkout, for example
``v26.10.18.64+ff96b16``. It is shown in the window's status bar and printed
first by ``--debug``. Never raises: a label is a convenience.
"""

from __future__ import annotations

import subprocess
import tomllib
from importlib import metadata
from pathlib import Path

UNKNOWN = "unknown"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _version(root: Path) -> str | None:
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return str(data["project"]["version"])
    except (OSError, KeyError, ValueError):
        pass
    try:
        return metadata.version("kuulas")
    except metadata.PackageNotFoundError:
        return None


def _git(root: Path, *args: str) -> str | None:
    try:
        # Fixed git arguments from this file only, in the code's own checkout.
        done = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=root, capture_output=True, text=True, timeout=3, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def build_label(root: Path | None = None) -> str:
    """``v<version>+<commit>[+dirty]`` (or just ``v<version>``, or ``unknown``)."""
    root = root if root is not None else _repo_root()
    version = _version(root) if root.exists() else None
    if version is None:
        return UNKNOWN
    label = f"v{version}"
    commit = _git(root, "rev-parse", "--short", "HEAD") if root.exists() else None
    if commit:
        label += f"+{commit}"
        if _git(root, "status", "--porcelain"):
            label += "+dirty"
    return label
