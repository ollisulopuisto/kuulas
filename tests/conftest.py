"""Shared test setup."""

import os
import tempfile
from pathlib import Path

import pytest

from kuulas import messages

# Mastering tests (pedalboard / speechmix) compile Numba kernels. On a clean machine
# or inside a restricted sandbox, the source tree is not writable, so set a writable
# cache directory in temp if one was not already provided by the environment.
_cache_dir = Path(os.environ.get("NUMBA_CACHE_DIR")
                  or Path(tempfile.gettempdir()) / "kuulas-numba-cache")
_cache_dir.mkdir(parents=True, exist_ok=True)
os.environ["NUMBA_CACHE_DIR"] = str(_cache_dir)


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
