"""Tests for transcript_find.py."""

import time

import pytest

from kuulas import transcript_find as tf


def _word(text: str, track: str = "t", clip: str = "c", index: int = 0) -> dict:
    """Build a timeline_words entry."""
    return {"w": text, "track": track, "clip": clip, "index": index}


def _words(*texts: str, track: str = "t") -> list[dict]:
    return [_word(text, track=track, index=i) for i, text in enumerate(texts)]


@pytest.mark.parametrize(("text", "expected"), [
    ("Määrä", "maara"),
    ("ÖljyÅ", "oljya"),
    ("hello, WORLD! 123", "hello world 123"),
    ("", ""),
])
def test_normalise(text: str, expected: str):
    assert tf.normalise(text) == expected


def test_find_single_word_prefix():
    words = _words("Kiitos!", "paljon")
    assert tf.find(words, "kiit") == ((0,),)
    assert tf.find(words, "KIIT") == ((0,),)
    assert tf.find(words, "k") == ()
    assert tf.find(words, "paljon") == ((1,),)


def test_find_accented_prefix():
    words = _words("määrä")
    assert tf.find(words, "maar") == ((0,),)
    assert tf.find(words, "määr") == ((0,),)


def test_find_multiword():
    words = _words("Kiitos", "paljon", "avusta")
    assert tf.find(words, "kiitos paljon") == ((0, 1),)
    assert tf.find(words, "kiitos avusta") == ()
    assert tf.find(words, "paljon avusta") == ((1, 2),)


def test_find_multiword_prefix():
    words = _words("Kiitos", "paljon")
    assert tf.find(words, "kiit pal") == ((0, 1),)


def test_find_empty_or_punctuation_query():
    words = _words("hei")
    assert tf.find(words, "") == ()
    assert tf.find(words, "...") == ()
    assert tf.find(words, "   ") == ()


def test_find_multiword_not_across_tracks():
    words = [_word("kiitos", track="t1"), _word("paljon", track="t2")]
    assert tf.find(words, "kiitos paljon") == ()


def test_next_match_wraps():
    matches = ((0,), (2,), (5,))
    assert tf.next_match(matches, -1) == (0,)
    assert tf.next_match(matches, 0) == (2,)
    assert tf.next_match(matches, 4) == (5,)
    assert tf.next_match(matches, 5) == (0,)


def test_prev_match_wraps():
    matches = ((0,), (2,), (5,))
    assert tf.prev_match(matches, 6) == (5,)
    assert tf.prev_match(matches, 5) == (2,)
    assert tf.prev_match(matches, 1) == (0,)
    assert tf.prev_match(matches, 0) == (5,)


def test_next_prev_no_matches():
    assert tf.next_match((), 0) is None
    assert tf.prev_match((), 0) is None


def test_find_is_fast():
    words = [_word(f"word{i}", index=i) for i in range(5000)]
    start = time.perf_counter()
    matches = tf.find(words, "word4999")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert matches == ((4999,),)
    assert elapsed_ms < 50
