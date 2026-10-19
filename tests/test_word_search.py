"""Tests for word search in transcripts (T64)."""

from kuulas.word_search import coverage, find_hits


def test_single_word():
    words = [
        {"w": "Hei", "start": 1.0, "end": 1.5},
        {"w": "maailma", "start": 1.6, "end": 2.2},
    ]
    assert find_hits(words, "Hei") == [
        {"first": 0, "last": 0, "start": 1.0, "end": 1.5}
    ]
    assert find_hits(words, "maailma") == [
        {"first": 1, "last": 1, "start": 1.6, "end": 2.2}
    ]


def test_phrase():
    words = [
        {"w": "yksi", "start": 0.0, "end": 0.5},
        {"w": "kaksi", "start": 0.6, "end": 1.0},
        {"w": "kolme", "start": 1.1, "end": 1.5},
        {"w": "neljä", "start": 1.6, "end": 2.0},
    ]
    assert find_hits(words, "kaksi kolme") == [
        {"first": 1, "last": 2, "start": 0.6, "end": 1.5}
    ]


def test_punctuation():
    words = [
        {"w": "niinku,", "start": 0.5, "end": 1.0},
        {"w": "joo...", "start": 1.1, "end": 1.4},
        {"w": "\"totta!\"", "start": 1.5, "end": 2.0},
    ]
    assert find_hits(words, "niinku") == [
        {"first": 0, "last": 0, "start": 0.5, "end": 1.0}
    ]
    assert find_hits(words, "niinku,") == [
        {"first": 0, "last": 0, "start": 0.5, "end": 1.0}
    ]
    assert find_hits(words, "joo") == [
        {"first": 1, "last": 1, "start": 1.1, "end": 1.4}
    ]
    assert find_hits(words, "totta") == [
        {"first": 2, "last": 2, "start": 1.5, "end": 2.0}
    ]
    assert find_hits(words, "niinku joo") == [
        {"first": 0, "last": 1, "start": 0.5, "end": 1.4}
    ]


def test_case():
    words = [
        {"w": "Ääni", "start": 0.0, "end": 0.8},
        {"w": "ÖLJY", "start": 1.0, "end": 1.6},
    ]
    assert find_hits(words, "ääni") == [
        {"first": 0, "last": 0, "start": 0.0, "end": 0.8}
    ]
    assert find_hits(words, "ÄÄNI") == [
        {"first": 0, "last": 0, "start": 0.0, "end": 0.8}
    ]
    assert find_hits(words, "öljy") == [
        {"first": 1, "last": 1, "start": 1.0, "end": 1.6}
    ]


def test_no_match():
    words = [{"w": "kissa", "start": 0.0, "end": 0.5}]
    assert find_hits(words, "koira") == []
    assert find_hits(words, "kissa koira") == []


def test_empty_query():
    words = [{"w": "kissa", "start": 0.0, "end": 0.5}]
    assert find_hits(words, "") == []
    assert find_hits(words, "   ") == []
    assert find_hits(words, ", . !") == []
    assert find_hits([], "kissa") == []


def test_overlapping_windows_union():
    hit = {"first": 0, "last": 1, "start": 1.5, "end": 3.5}
    # Unordered, overlapping windows whose union is [1.0, 4.0]
    windows = [(2.0, 4.0), (1.0, 3.0)]
    assert coverage(hit, windows) == "in"

    # Windows with a gap between [2.0, 3.0]
    windows_gap = [(1.0, 2.0), (3.0, 4.0)]
    assert coverage(hit, windows_gap) == "partly"


def test_hit_on_window_edge_inside():
    windows = [(1.0, 5.0)]
    # Matches both edges exactly
    assert coverage({"first": 0, "last": 0, "start": 1.0, "end": 5.0}, windows) == "in"
    # Matches left edge
    assert coverage({"first": 0, "last": 0, "start": 1.0, "end": 3.0}, windows) == "in"
    # Matches right edge
    assert coverage({"first": 0, "last": 0, "start": 3.0, "end": 5.0}, windows) == "in"


def test_zero_length_windows_ignored():
    hit = {"first": 0, "last": 0, "start": 2.0, "end": 3.0}
    # Only zero-length or inverted windows
    assert coverage(hit, [(2.0, 2.0), (5.0, 2.0)]) == "cut"
    # Zero-length alongside a valid window
    assert coverage(hit, [(2.0, 2.0), (1.0, 4.0)]) == "in"


def test_cut_and_partly():
    hit = {"first": 0, "last": 0, "start": 10.0, "end": 12.0}
    assert coverage(hit, [(0.0, 5.0), (6.0, 8.0)]) == "cut"

    hit_partial = {"first": 0, "last": 0, "start": 4.0, "end": 6.0}
    assert coverage(hit_partial, [(0.0, 5.0)]) == "partly"
