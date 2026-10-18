"""Editing the status list: rename, add, remove, move, set_done, labels
and ensure_current.

A status list is a tuple of ``(label, done)`` pairs; every function returns
a new tuple and leaves its input alone. Labels are stored normalised
(stripped, whitespace collapsed); lookups match case-insensitively as
given.
"""

import pytest

from kuulas.status_settings import (
    add,
    ensure_current,
    labels,
    move,
    remove,
    rename,
    set_done,
)

LIST = (
    ("Draft", False),
    ("In review", False),
    ("Published", True),
)


# -- rename -----------------------------------------------------------------


def test_rename_replaces_the_label_and_keeps_position_and_done():
    result = rename(LIST, "In review", "Katsauksessa")
    assert result == (
        ("Draft", False),
        ("Katsauksessa", False),
        ("Published", True),
    )


def test_rename_matches_the_old_label_case_insensitively():
    result = rename(LIST, "PUBLISHED", "Julkaistu")
    assert result[-1] == ("Julkaistu", True)


def test_rename_normalises_the_new_label():
    result = rename(LIST, "Draft", "  Luonnos   valmis  ")
    assert result[0] == ("Luonnos valmis", False)


def test_rename_to_an_empty_new_label_raises():
    with pytest.raises(ValueError, match="label cannot be empty"):
        rename(LIST, "Draft", "")
    with pytest.raises(ValueError, match="label cannot be empty"):
        rename(LIST, "Draft", "   ")


def test_rename_with_an_unknown_old_label_raises():
    with pytest.raises(ValueError, match="unknown status label"):
        rename(LIST, "Archived", "Arkistoitu")


def test_rename_to_another_existing_label_raises():
    with pytest.raises(ValueError, match="duplicate status label"):
        rename(LIST, "Draft", "Published")
    # Case-insensitively another existing label.
    with pytest.raises(ValueError, match="duplicate status label"):
        rename(LIST, "Draft", "PUBLISHED")


def test_rename_case_only_is_allowed():
    result = rename(LIST, "Draft", "DRAFT")
    assert result == (
        ("DRAFT", False),
        ("In review", False),
        ("Published", True),
    )


# -- add --------------------------------------------------------------------


def test_add_appends_as_not_done_by_default():
    result = add(LIST, "Archived")
    assert result == (
        ("Draft", False),
        ("In review", False),
        ("Published", True),
        ("Archived", False),
    )


def test_add_appends_as_done_when_asked():
    assert add((), "Published", True) == (("Published", True),)


def test_add_to_an_empty_list():
    assert add((), "Draft") == (("Draft", False),)


def test_add_normalises_the_label():
    assert add((), "  Ready   for  review ") == (("Ready for review", False),)


def test_add_with_an_empty_label_raises():
    with pytest.raises(ValueError, match="label cannot be empty"):
        add(LIST, "")
    with pytest.raises(ValueError, match="label cannot be empty"):
        add(LIST, "   ")


def test_add_with_a_duplicate_label_raises():
    with pytest.raises(ValueError, match="duplicate status label"):
        add(LIST, "Draft")
    # Case-insensitively a duplicate.
    with pytest.raises(ValueError, match="duplicate status label"):
        add(LIST, "pUBLISHED")
    # A duplicate only after normalisation.
    with pytest.raises(ValueError, match="duplicate status label"):
        add(LIST, "  in   review ")


# -- remove -----------------------------------------------------------------


def test_remove_removes_the_pair():
    result = remove(LIST, "In review")
    assert result == (("Draft", False), ("Published", True))


def test_remove_matches_case_insensitively():
    assert remove(LIST, "draft") == (
        ("In review", False),
        ("Published", True),
    )


def test_remove_with_an_unknown_label_raises():
    with pytest.raises(ValueError, match="unknown status label"):
        remove(LIST, "Archived")


def test_remove_the_last_remaining_status_raises():
    only_draft = (("Draft", False),)
    with pytest.raises(ValueError, match="cannot remove the last"):
        remove(only_draft, "Draft")
    # An unknown label on a one-pair list reports unknown, not last.
    with pytest.raises(ValueError, match="unknown status label"):
        remove(only_draft, "Published")


# -- move -------------------------------------------------------------------


def test_move_places_the_pair_at_the_index():
    assert move(LIST, "Draft", 1) == (
        ("In review", False),
        ("Draft", False),
        ("Published", True),
    )
    assert move(LIST, "Published", 0) == (
        ("Published", True),
        ("Draft", False),
        ("In review", False),
    )


def test_move_clamps_a_negative_index_to_zero():
    assert move(LIST, "Published", -5) == (
        ("Published", True),
        ("Draft", False),
        ("In review", False),
    )


def test_move_clamps_a_too_large_index_to_the_end():
    assert move(LIST, "Draft", 99) == (
        ("In review", False),
        ("Published", True),
        ("Draft", False),
    )


def test_move_to_the_same_index_changes_nothing():
    assert move(LIST, "In review", 1) == LIST


def test_move_with_an_unknown_label_raises():
    with pytest.raises(ValueError, match="unknown status label"):
        move(LIST, "Archived", 0)


# -- set_done ---------------------------------------------------------------


def test_set_done_changes_done_and_keeps_the_stored_label():
    # The stored label keeps its own case and position; only done moves.
    result = set_done(LIST, "PUBLISHED", False)
    assert result == (
        ("Draft", False),
        ("In review", False),
        ("Published", False),
    )
    result = set_done(LIST, "draft", True)
    assert result[0] == ("Draft", True)


def test_set_done_with_an_unknown_label_raises():
    with pytest.raises(ValueError, match="unknown status label"):
        set_done(LIST, "Archived", True)


# -- labels -----------------------------------------------------------------


def test_labels_returns_the_labels_in_order():
    assert labels(LIST) == ("Draft", "In review", "Published")


def test_labels_of_an_empty_list_is_empty():
    assert labels(()) == ()


# -- ensure_current ---------------------------------------------------------


def test_ensure_current_with_a_known_label_returns_an_equal_list():
    assert ensure_current(LIST, "In review") == LIST


def test_ensure_current_returns_a_new_tuple_even_when_known():
    result = ensure_current(LIST, "Draft")
    assert result == LIST
    assert result is not LIST


def test_ensure_current_matches_case_insensitively():
    assert ensure_current(LIST, "PUBLISHED") == LIST


def test_ensure_current_normalises_before_matching():
    # The label normalises to one the list already has, so nothing is
    # appended.
    assert ensure_current(LIST, "  published  ") == LIST


def test_ensure_current_appends_an_unknown_label_as_not_done():
    result = ensure_current(LIST, "Julkaisussa")
    assert result == (
        ("Draft", False),
        ("In review", False),
        ("Published", True),
        ("Julkaisussa", False),
    )


def test_ensure_current_normalises_the_appended_label():
    result = ensure_current((), "  Julkaisu   valmis ")
    assert result == (("Julkaisu valmis", False),)


def test_ensure_current_with_an_empty_label_raises():
    with pytest.raises(ValueError, match="label cannot be empty"):
        ensure_current(LIST, "")


# -- immutability -----------------------------------------------------------


def test_every_function_leaves_its_input_unchanged():
    rename(LIST, "Draft", "Luonnos")
    add(LIST, "Archived", True)
    remove(LIST, "Draft")
    move(LIST, "Draft", 2)
    set_done(LIST, "Draft", True)
    labels(LIST)
    ensure_current(LIST, "Archived")
    assert LIST == (
        ("Draft", False),
        ("In review", False),
        ("Published", True),
    )
