"""Narration estimate (WP43)."""

import pytest

from kuulas.messages import KuulasError
from kuulas.narration import count_words, estimate_frames

RATE = 48_000


def test_count_words():
    assert count_words("Päivää, kaikki!") == 2
    assert count_words("e-mail") == 1
    assert count_words("don't") == 1
    assert count_words("3.5") == 1
    assert count_words("") == 0
    assert count_words("   ") == 0


def test_estimate_frames_twenty_three_words():
    text = ("The quick brown fox jumps over the lazy dog and runs fast "
            "through the green field while the sun shines bright up high")
    assert count_words(text) == 23
    assert estimate_frames(text, RATE, 2.3) == 480_000


def test_single_word_is_one_second_minimum():
    assert estimate_frames("Hello", RATE) == RATE


def test_empty_or_blank_text_is_zero_frames():
    assert estimate_frames("", RATE) == 0
    assert estimate_frames("   \t\n", RATE) == 0


def test_bad_words_per_second_raises():
    with pytest.raises(KuulasError) as exc:
        estimate_frames("Hello", RATE, 0.0)
    assert exc.value.key == "error.narration.bad_words_per_second"
    with pytest.raises(KuulasError):
        estimate_frames("Hello", RATE, -1.0)


def test_curly_apostrophe_is_one_word():
    assert count_words("don\u2019t") == 1
