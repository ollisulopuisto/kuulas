"""Shared test setup."""

import getpass
import os
import tempfile
from pathlib import Path

import pytest

from kuulas import messages


def _writable(path: Path) -> bool:
    """Can we create and delete a file in ``path`` (creating it if needed)?"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError:
        return False
    return True


def _numba_cache_dir() -> Path:
    """A writable Numba cache folder, chosen before Numba is imported.

    The mastering tests compile Numba kernels. On a clean machine or in a
    restricted sandbox the default cache next to the source is not writable.
    An explicit ``NUMBA_CACHE_DIR`` is used if it works; otherwise a per-user
    folder in the temp directory (per user, so one account's folder never
    blocks or poisons another's).
    """
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = "shared"
    for candidate in (os.environ.get("NUMBA_CACHE_DIR"),
                      Path(tempfile.gettempdir()) / f"kuulas-numba-{user}"):
        if candidate and _writable(Path(candidate)):
            return Path(candidate)
    raise RuntimeError("no writable folder for the Numba cache; set NUMBA_CACHE_DIR")


os.environ["NUMBA_CACHE_DIR"] = str(_numba_cache_dir())


@pytest.fixture(autouse=True)
def _english_messages():
    """Every test starts in English and leaves the language as it found it.

    The default language follows the machine (Finnish on the owner's Mac), and
    ``set_language`` is process-wide, so without this a test that asserts
    English text passes or fails depending on which test ran before it.
    Tests that need Finnish call ``set_language("fi")`` themselves.
    """
    before = messages.language()
    messages.set_language("en")
    try:
        yield
    finally:
        messages.set_language(before)
