"""Unique names for new tracks and clips."""

import pytest

from kuulas.unique_name import unique_name


def test_free_base_is_returned_unchanged():
    assert unique_name("Olli", {"Pekka", "Jaana"}) == "Olli"


def test_case_insensitive_compare():
    assert unique_name("Olli", {"olli"}) == "Olli 2"
    assert unique_name("OLLI", {"Olli"}) == "OLLI 2"


def test_taken_base_gets_first_free_number():
    assert unique_name("Olli", {"Olli"}) == "Olli 2"
    assert unique_name("Olli", {"Olli", "Olli 2"}) == "Olli 3"
    assert unique_name("Olli", {"Olli", "Olli 2", "Olli 4"}) == "Olli 3"


def test_trailing_number_continues_from_the_stem():
    assert unique_name("Olli 2", {"Olli 2"}) == "Olli 3"
    assert unique_name("Olli 2", {"Olli 2", "Olli 3"}) == "Olli 4"
    assert unique_name("Olli 2", {"Olli 2 2"}) == "Olli 2"


def test_strips_surrounding_whitespace():
    assert unique_name("  Olli  ", {"olli"}) == "Olli 2"
    assert unique_name("\tOlli\n", {"Olli"}) == "Olli 2"


def test_empty_base_raises_value_error():
    with pytest.raises(ValueError, match="empty"):
        unique_name("", {"Olli"})
    with pytest.raises(ValueError, match="empty"):
        unique_name("   ", {"Olli"})


def test_existing_is_not_mutated_and_accepts_any_iterable():
    existing = ["Olli", "Olli 2"]
    before = list(existing)
    assert unique_name("Olli", existing) == "Olli 3"
    assert existing == before
    assert unique_name("Olli", iter(["Olli"])) == "Olli 2"
    assert unique_name("Olli", (name for name in ["Olli"])) == "Olli 2"
