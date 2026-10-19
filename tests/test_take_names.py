"""Names for takes."""

from datetime import UTC, datetime

import pytest

from kuulas.take_names import (
    file_stem,
    take_name,
    timestamp_stem,
    unique_file_names,
)


def test_take_name_starts_at_one():
    assert take_name([], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 1"


def test_take_name_counts_existing_takes():
    assert take_name(["Take 1"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 2"
    assert take_name(["Take 1", "Take 2"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 3"


def test_take_name_is_case_insensitive():
    assert take_name(["take 3"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 4"
    assert take_name(["TAKE 4"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 5"


def test_take_name_ignores_extra_text_after_the_number():
    assert take_name(["take 7 (bad)"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 8"


def test_take_name_takes_the_highest_number():
    assert (
        take_name(["Take 1", "take 7 (bad)", "Take 2"], datetime(2026, 1, 1, tzinfo=UTC))
        == "Take 8"
    )
    assert take_name(["Take 1", "Take 5"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 6"


def test_take_name_zero_and_non_take_names():
    assert take_name(["Take 0"], datetime(2026, 1, 1, tzinfo=UTC)) == "Take 1"
    assert (
        take_name(["Take", "Recording 5", "take"], datetime(2026, 1, 1, tzinfo=UTC))
        == "Take 1"
    )


def test_take_name_rejects_non_strings():
    with pytest.raises(ValueError, match="must be a string"):
        take_name(["Take 1", 5], datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="must be a string"):
        take_name([None], datetime(2026, 1, 1, tzinfo=UTC))


def test_file_stem_joins_take_and_track():
    assert file_stem("Take 3", "Olli") == "Take 3 Olli"


def test_file_stem_empty_track_is_just_the_take():
    assert file_stem("Take 1", "") == "Take 1"


def test_file_stem_passes_finnish_letters_through():
    assert file_stem("Take 2", "Ääni") == "Take 2 Ääni"


def test_file_stem_replaces_illegal_characters():
    assert file_stem("Take 1", "Olli/Matti") == "Take 1 Olli-Matti"


def test_file_stem_is_cut_to_max_len_80():
    stem = file_stem("Take 1", "x" * 100)
    assert len(stem) <= 80
    assert stem.startswith("Take 1 ")


def test_file_stem_rejects_non_strings():
    with pytest.raises(ValueError, match="must be a string"):
        file_stem(5, "Olli")
    with pytest.raises(ValueError, match="must be a string"):
        file_stem("Take 1", 5)


def test_timestamp_stem_format():
    assert (
        timestamp_stem(datetime(2026, 10, 19, 13, 6, 0, tzinfo=UTC))
        == "2026-10-19 130600"
    )


def test_timestamp_stem_midnight():
    assert (
        timestamp_stem(datetime(2026, 1, 5, 0, 0, 0, tzinfo=UTC))
        == "2026-01-05 000000"
    )


def test_timestamp_stem_uses_24_hour_clock():
    assert (
        timestamp_stem(datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC))
        == "2026-12-31 235959"
    )


def test_unique_file_names_adds_wav():
    assert unique_file_names(["Take 3 Olli"], []) == ["Take 3 Olli.wav"]


def test_unique_file_names_is_unique_against_existing_case_insensitive():
    assert unique_file_names(["Take 1"], ["take 1.wav"]) == ["Take 1.wav 2"]


def test_unique_file_names_duplicate_stems_get_numbers():
    assert unique_file_names(["Take 1", "Take 1"], []) == [
        "Take 1.wav",
        "Take 1.wav 2",
    ]


def test_unique_file_names_preserves_order():
    assert unique_file_names(["B take", "A take"], ["a take.wav"]) == [
        "B take.wav",
        "A take.wav 2",
    ]


def test_unique_file_names_empty():
    assert unique_file_names([], ["a.wav"]) == []


def test_unique_file_names_does_not_mutate_input():
    stems = ["Take 1"]
    existing = ["take 1.wav"]
    unique_file_names(stems, existing)
    assert stems == ["Take 1"]
    assert existing == ["take 1.wav"]


def test_unique_file_names_rejects_non_strings():
    with pytest.raises(ValueError, match="must be a string"):
        unique_file_names(["Take 1", 5], [])
    with pytest.raises(ValueError, match="must be a string"):
        unique_file_names(["Take 1"], [5])
