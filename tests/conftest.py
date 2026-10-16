"""Shared test setup."""

import pytest

from kuulas import messages


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
