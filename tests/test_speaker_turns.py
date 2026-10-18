"""Speaker turns from timed words: speaker_turns.

Pure Python, stdlib only, no imports from kuulas. Errors are plain
ValueError; there is no user-facing text. Inputs are never mutated.
"""

import pytest

from kuulas.speaker_turns import speaker_turns


def test_empty_list_gives_no_turns():
    assert speaker_turns([], 0.5) == []


def test_single_word_is_one_turn():
    assert speaker_turns([{"speaker": "A", "s": 0, "e": 10}], 0.5) == [
        {"speaker": "A", "s": 0, "e": 10, "words": 1}
    ]


def test_same_speaker_within_gap_is_one_turn():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 10},
            {"speaker": "A", "s": 14, "e": 20},
        ],
        5,
    ) == [{"speaker": "A", "s": 0, "e": 20, "words": 2}]


def test_gap_exactly_max_gap_is_one_turn():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 10},
            {"speaker": "A", "s": 15, "e": 20},
        ],
        5,
    ) == [{"speaker": "A", "s": 0, "e": 20, "words": 2}]


def test_same_speaker_beyond_gap_is_two_turns():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 10},
            {"speaker": "A", "s": 16, "e": 20},
        ],
        5,
    ) == [
        {"speaker": "A", "s": 0, "e": 10, "words": 1},
        {"speaker": "A", "s": 16, "e": 20, "words": 1},
    ]


def test_different_speaker_starts_new_turn():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 10},
            {"speaker": "B", "s": 10, "e": 20},
        ],
        100,
    ) == [
        {"speaker": "A", "s": 0, "e": 10, "words": 1},
        {"speaker": "B", "s": 10, "e": 20, "words": 1},
    ]


def test_contained_word_keeps_turn_end_at_max():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 100},
            {"speaker": "A", "s": 50, "e": 80},
        ],
        0,
    ) == [{"speaker": "A", "s": 0, "e": 100, "words": 2}]


def test_overlapping_words_merge_into_one_turn():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 100},
            {"speaker": "A", "s": 50, "e": 150},
        ],
        0,
    ) == [{"speaker": "A", "s": 0, "e": 150, "words": 2}]


def test_mixed_speakers_form_turns_in_order():
    assert speaker_turns(
        [
            {"speaker": "A", "s": 0, "e": 5},
            {"speaker": "B", "s": 6, "e": 11},
            {"speaker": "A", "s": 12, "e": 17},
        ],
        2,
    ) == [
        {"speaker": "A", "s": 0, "e": 5, "words": 1},
        {"speaker": "B", "s": 6, "e": 11, "words": 1},
        {"speaker": "A", "s": 12, "e": 17, "words": 1},
    ]


def test_max_gap_negative_raises_value_error():
    with pytest.raises(ValueError, match="max_gap"):
        speaker_turns([{"speaker": "A", "s": 0, "e": 10}], -0.1)


def test_end_before_start_raises_value_error():
    with pytest.raises(ValueError, match="end"):
        speaker_turns([{"speaker": "A", "s": 10, "e": 5}], 1)


def test_out_of_order_words_raise_value_error():
    with pytest.raises(ValueError, match="time order"):
        speaker_turns(
            [
                {"speaker": "A", "s": 10, "e": 20},
                {"speaker": "A", "s": 5, "e": 15},
            ],
            1,
        )


def test_input_is_not_mutated():
    words = [
        {"speaker": "A", "s": 0, "e": 10},
        {"speaker": "A", "s": 14, "e": 20},
    ]
    copy = [
        {"speaker": "A", "s": 0, "e": 10},
        {"speaker": "A", "s": 14, "e": 20},
    ]
    speaker_turns(words, 5)
    assert words == copy
    assert words[0] == copy[0]
