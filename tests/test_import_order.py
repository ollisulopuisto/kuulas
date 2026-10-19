"""Every entry module imports on its own with no locale variables set (an app started
from Finder has none), so the language setting is read before anything else is loaded."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

MODULES = ["kuulas.cli", "kuulas.messages", "kuulas.db", "kuulas.package",
           "kuulas.bundle", "kuulas.desktop", "kuulas.server"]


@pytest.mark.parametrize("module", MODULES)
def test_a_module_imports_first_without_locale_variables(module, tmp_path):
    env = {k: v for k, v in os.environ.items()
           if k not in ("LC_ALL", "LC_MESSAGES", "KUULAS_SETTINGS_FILE")}
    env["HOME"] = str(tmp_path)  # no settings file there either
    done = subprocess.run(  # noqa: S603 - our own interpreter, a fixed command
        [sys.executable, "-c", f"import {module}"], env=env,
        capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-800:]


def test_the_language_is_not_looked_up_at_import(tmp_path):
    """Looking it up on macOS runs `defaults read` (a subprocess): not at import time."""
    code = ("import kuulas.messages as m; assert m._language is None; "
            "m.language(); assert m._language is not None")
    done = subprocess.run(  # noqa: S603 - our own interpreter, a fixed command
        [sys.executable, "-c", code], env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-800:]
