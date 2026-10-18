"""Words and time ranges (logic only).

Pure Python, stdlib only: no imports from kuulas. Errors are plain ValueError;
there is no user-facing text.
"""

import pytest

from kuulas.word_ranges import ranges_of_words, words_in_ranges


def test_words_in_ranges_empty_words_gives_empty():
    assert words_in_ranges([], [(0, 100)]) == []


def test_words_in_ranges_empty_ranges_gives_empty():
    assert words_in_ranges([{"s": 0, "e": 10}], []) == []


def test_words_in_ranges_keeps_words_whose_midpoint_is_in_range():
    words = [
        {"s": 0, "e": 100, "text": "before"},    # midpoint 50, excluded
        {"s": 100, "e": 300, "text": "inside"},   # midpoint 200, included
        {"s": 400, "e": 500, "text": "after"},    # midpoint 450, excluded
    ]
    assert [w["text"] for w in words_in_ranges(words, [(150, 250)])] == [
        "inside"
    ]


def test_words_in_ranges_start_inclusive_end_exclusive():
    words = [
        {"s": 190, "e": 210, "text": "at start"},   # midpoint 200
        {"s": 290, "e": 310, "text": "at end"},      # midpoint 300
    ]
    kept = words_in_ranges(words, [(200, 300)])
    assert [w["text"] for w in kept] == ["at start"]


def test_words_in_ranges_word_in_any_of_several_ranges():
    words = [
        {"s": 0, "e": 40, "text": "first"},     # midpoint 20
        {"s": 90, "e": 110, "text": "second"},  # midpoint 100
        {"s": 190, "e": 210, "text": "third"},  # midpoint 200
    ]
    kept = words_in_ranges(words, [(0, 50), (90, 150)])
    assert [w["text"] for w in kept] == ["first", "second"]


def test_words_in_ranges_keeps_input_order():
    words = [
        {"s": 190, "e": 210, "text": "later range first"},   # midpoint 200
        {"s": 0, "e": 40, "text": "first range first"},      # midpoint 20
    ]
    kept = words_in_ranges(words, [(0, 50), (150, 250)])
    assert [w["text"] for w in kept] == ["later range first", "first range first"]


def test_words_in_ranges_returns_shallow_copies():
    original = [{"s": 100, "e": 300, "text": "keep"}]
    kept = words_in_ranges(original, [(200, 250)])
    assert kept is not original
    assert kept[0] is not original[0]
    kept[0]["text"] = "changed"
    assert original[0]["text"] == "keep"


def test_words_in_ranges_bad_range_raises_value_error():
    with pytest.raises(ValueError, match="range"):
        words_in_ranges([{"s": 0, "e": 10}], [(5, 5)])
    with pytest.raises(ValueError, match="range"):
        words_in_ranges([{"s": 0, "e": 10}], [(10, 5)])


def test_ranges_of_words_empty_gives_empty():
    assert ranges_of_words([]) == []


def test_ranges_of_words_single_word_no_pad():
    assert ranges_of_words([{"s": 100, "e": 200}]) == [(100, 200)]


def test_ranges_of_words_pad_widens_both_sides():
    assert ranges_of_words([{"s": 100, "e": 200}], pad=10.0) == [(90.0, 210.0)]


def test_ranges_of_words_start_is_clamped_at_zero():
    assert ranges_of_words([{"s": 5, "e": 20}], pad=10.0) == [(0, 30)]


def test_ranges_of_words_sorts_by_s():
    words = [
        {"s": 200, "e": 300, "text": "later"},
        {"s": 0, "e": 100, "text": "first"},
    ]
    assert ranges_of_words(words) == [(0, 100), (200, 300)]


def test_ranges_of_words_merges_when_gap_is_at_most_join_gap():
    words = [
        {"s": 0, "e": 100},
        {"s": 150, "e": 250},   # gap 50
        {"s": 310, "e": 400},   # gap 60 from the merged end
    ]
    assert ranges_of_words(words, join_gap=50.0) == [(0, 250), (310, 400)]
    assert ranges_of_words(words, join_gap=60.0) == [(0, 400)]


def test_ranges_of_words_touching_ranges_merge_with_zero_join_gap():
    assert ranges_of_words([{"s": 0, "e": 100}, {"s": 100, "e": 200}]) == [
        (0, 200)
    ]


def test_ranges_of_words_pad_applied_before_merge():
    words = [
        {"s": 0, "e": 100},
        {"s": 121, "e": 220},
    ]
    assert ranges_of_words(words, join_gap=5.0) == [(0, 100), (121, 220)]
    assert ranges_of_words(words, pad=10.0, join_gap=5.0) == [(0, 230)]


def test_ranges_of_words_negative_pad_raises_value_error():
    with pytest.raises(ValueError, match="pad"):
        ranges_of_words([{"s": 0, "e": 10}], pad=-1.0)


def test_ranges_of_words_negative_join_gap_raises_value_error():
    with pytest.raises(ValueError, match="join_gap"):
        ranges_of_words([{"s": 0, "e": 10}], join_gap=-1.0)


def test_ranges_of_words_does_not_mutate_input():
    original = [{"s": 100, "e": 200, "text": "w"}]
    before = [dict(w) for w in original]
    ranges_of_words(original, pad=10.0, join_gap=5.0)
    assert original == before
