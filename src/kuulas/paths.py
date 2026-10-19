"""Where kuulas finds its own files at run time (WP73).

The same code runs from three layouts, and the UI files (``ui/``, served at ``/``)
are in a different place in each:

- inside the package (``kuulas/ui``): a wheel built with the UI as package data;
- beside the package (``app/kuulas`` and ``app/ui``): the Briefcase bundle, which
  copies each source folder into ``Resources/app``;
- at the repo root (``src/kuulas`` and ``ui``): a checkout, ``uv run`` and the tests.
"""

from __future__ import annotations

from pathlib import Path


def find_ui_dir(module_file: str | Path) -> Path:
    """The first of the three places above that holds an ``index.html``. When none
    does, the checkout location: the server then says plainly that the UI is
    missing, naming the folder a developer expects."""
    package = Path(module_file).resolve().parent
    repo_guess = package.parents[1] / "ui"
    for candidate in (package / "ui", package.parent / "ui", repo_guess):
        if (candidate / "index.html").is_file():
            return candidate
    return repo_guess
