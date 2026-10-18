"""Excerpts for copying media between projects (WP20, logic only).

Pure Python, stdlib only: no imports from kuulas.
"""

import pytest

from kuulas.excerpt_media import (
    excerpt_origin,
    excerpt_window,
    flicks,
    shift_offset,
    slice_words,
)


def test_excerpt_window_with_one_range_is_widened_by_the_handle():
    # handle: 0.01 s at 1000 frames/s = 10 frames each side
    start, end = excerpt_window([(100, 200)], 0.01, 1000, 10_000)
    assert (start, end) == (90, 210)


def test_excerpt_window_with_several_ranges_takes_their_union():
    start, end = excerpt_window([(100, 200), (500, 600), (300, 400)], 0.01, 1000, 10_000)
    assert (start, end) == (90, 610)


def test_excerpt_window_handle_is_clamped_at_both_ends():
    start, end = excerpt_window([(100, 200)], 1.0, 1000, 10_000)
    assert (start, end) == (0, 1200)
    start, end = excerpt_window([(9_800, 9_900)], 1.0, 1000, 10_000)
    assert (start, end) == (8800, 10_000)


def test_excerpt_window_empty_ranges_raises_value_error():
    with pytest.raises(ValueError, match="ranges"):
        excerpt_window([], 0.01, 1000, 10_000)


def test_shift_offset_subtracts_the_excerpt_start():
    assert shift_offset(250, 100) == 150
    assert shift_offset(100, 100) == 0


def test_shift_offset_negative_result_raises_value_error():
    with pytest.raises(ValueError, match="negative"):
        shift_offset(50, 100)


def test_flicks_at_48000_and_44100():
    assert flicks(48_000, 48_000) == 705_600_000
    assert flicks(1, 48_000) == 14_700
    assert flicks(44_100, 44_100) == 705_600_000
    assert flicks(1, 44_100) == 16_000


def test_flicks_uses_integer_maths():
    assert flicks(1, 3) == 705_600_000 // 3


def test_slice_words_keeps_words_whose_midpoint_is_in_range():
    words = [
        {"s": 0, "e": 1000, "text": "before"},      # midpoint 500, excluded
        {"s": 1000, "e": 2000, "text": "at start"},  # midpoint 1500, included
        {"s": 0, "e": 2000, "text": "straddles"},    # midpoint 1000, included
        {"s": 4000, "e": 5000, "text": "at end"},    # midpoint 4500, excluded
    ]
    kept = slice_words(words, 1000, 4000)
    assert [w["text"] for w in kept] == ["at start", "straddles"]
    assert kept[0]["s"] == 0
    assert kept[0]["e"] == 1000
    assert kept[1]["s"] == -1000
    assert kept[1]["e"] == 1000


def test_slice_words_excludes_a_word_at_end_flicks():
    words = [{"s": 3000, "e": 5000, "text": "ends exactly"}]
    assert slice_words(words, 1000, 4000) == []


def test_slice_words_returns_copies_and_does_not_mutate_the_input():
    original = [{"s": 1000, "e": 2000, "text": "kept", "extra": 1}]
    kept = slice_words(original, 1000, 4000)
    assert kept is not original
    assert kept[0] is not original[0]
    kept[0]["s"] = 999
    assert original[0]["s"] == 1000
    assert original[0]["extra"] == 1


def test_excerpt_origin_adds_the_excerpt_start():
    assert excerpt_origin(5000, 1000) == 6000
    assert excerpt_origin(0, 1000) == 1000
    assert excerpt_origin(12345, 0) == 12345
