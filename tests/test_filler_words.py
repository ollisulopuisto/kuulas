"""Filler word detection in a transcript.

Pure Python, stdlib only, no imports from kuulas. Errors are plain ValueError;
there is no user-facing text.
"""

import pytest

from kuulas.filler_words import DEFAULT_FILLERS, find_fillers, merge_runs


def w(text, start, end):
    return {"text": text, "start": start, "end": end}


def test_default_filllers_are_lower_case():
    assert DEFAULT_FILLERS == ("öö", "ööö", "öh", "mm", "mmm", "hmm",
                               "um", "uh", "er", "erm", "niinku", "tota")
    assert all(f == f.lower() for f in DEFAULT_FILLERS)


def test_finds_exact_filler():
    assert find_fillers([w("öö", 0, 4800)]) == [
        {"index": 0, "text": "öö", "start": 0, "end": 4800}]


def test_case_insensitive():
    assert find_fillers([w("ÖÖ", 0, 4800)]) == [
        {"index": 0, "text": "ÖÖ", "start": 0, "end": 4800}]


def test_strips_leading_and_trailing_punctuation():
    assert find_fillers([w('"öö,"', 0, 4800)]) == [
        {"index": 0, "text": '"öö,"', "start": 0, "end": 4800}]
    assert find_fillers([w("öh!", 4800, 9600)]) == [
        {"index": 0, "text": "öh!", "start": 4800, "end": 9600}]


def test_all_default_filllers_match():
    words = [w(f, i * 4800, (i + 1) * 4800) for i, f in enumerate(DEFAULT_FILLERS)]
    found = find_fillers(words)
    assert [f["index"] for f in found] == list(range(len(DEFAULT_FILLERS)))


def test_repeated_letters_match_a_short_filler():
    assert find_fillers([w("ööööö", 0, 4800)]) == [
        {"index": 0, "text": "ööööö", "start": 0, "end": 4800}]
    assert find_fillers([w("mmmm", 0, 4800)]) == [
        {"index": 0, "text": "mmmm", "start": 0, "end": 4800}]


def test_repetition_needs_at_least_as_many_letters_as_the_filler():
    assert find_fillers([w("ö", 0, 4800)]) == []
    assert find_fillers([w("mm", 0, 4800)]) == [
        {"index": 0, "text": "mm", "start": 0, "end": 4800}]
    assert find_fillers([w("öö", 0, 4800), w("ööö", 4800, 9600),
                         w("öööö", 9600, 14400)]) == [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 1, "text": "ööö", "start": 4800, "end": 9600},
        {"index": 2, "text": "öööö", "start": 9600, "end": 14400}]


def test_not_a_filler():
    assert find_fillers([w("hello", 0, 4800)]) == []
    assert find_fillers([w("niinkuun", 0, 4800)]) == []
    assert find_fillers([w("tottua", 0, 4800)]) == []
    assert find_fillers([w("!!!  ...", 0, 4800)]) == []
    assert find_fillers([w("", 0, 4800)]) == []
    assert find_fillers([w("   ", 0, 4800)]) == []


def test_custom_filllers_are_lower_cased():
    assert find_fillers([w("ÖÖ", 0, 4800)], fillers=["ÖÖ"]) == [
        {"index": 0, "text": "ÖÖ", "start": 0, "end": 4800}]
    assert find_fillers([w("hmm", 0, 4800)], fillers=["hmm", "bla"]) == [
        {"index": 0, "text": "hmm", "start": 0, "end": 4800}]


def test_empty_filllers_find_nothing():
    assert find_fillers([w("öö", 0, 4800)], fillers=[]) == []
    assert find_fillers([w("öö", 0, 4800)], fillers=()) == []


def test_missing_word_key_raises_value_error():
    with pytest.raises(ValueError, match="text"):
        find_fillers([{"start": 0, "end": 4800}])
    with pytest.raises(ValueError, match="start"):
        find_fillers([{"text": "öö", "end": 4800}])
    with pytest.raises(ValueError, match="end"):
        find_fillers([{"text": "öö", "start": 0}])


def test_input_not_mutated():
    words = [w("öö", 0, 4800), w("hello", 4800, 9600)]
    before = [dict(w) for w in words]
    find_fillers(words)
    assert words == before


def test_merge_runs_empty():
    assert merge_runs([], 100) == []


def test_merge_runs_single():
    found = [w("öö", 0, 4800)]
    found[0] = {"index": 0, "text": "öö", "start": 0, "end": 4800}
    assert merge_runs(found, 100) == [
        {"start": 0, "end": 4800, "indexes": [0]}]


def test_merge_runs_joins_consecutive_with_small_gap():
    found = [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 1, "text": "mm", "start": 4900, "end": 9700},
    ]
    assert merge_runs(found, 100) == [
        {"start": 0, "end": 9700, "indexes": [0, 1]}]


def test_merge_runs_gap_too_large_stays_separate():
    found = [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 1, "text": "mm", "start": 5000, "end": 9800},
    ]
    assert merge_runs(found, 100) == [
        {"start": 0, "end": 4800, "indexes": [0]},
        {"start": 5000, "end": 9800, "indexes": [1]}]


def test_merge_runs_non_consecutive_indexes_stay_separate():
    found = [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 2, "text": "mm", "start": 4850, "end": 9650},
    ]
    assert merge_runs(found, 100) == [
        {"start": 0, "end": 4800, "indexes": [0]},
        {"start": 4850, "end": 9650, "indexes": [2]}]


def test_merge_runs_chain_of_three():
    found = [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 1, "text": "ö", "start": 4850, "end": 9650},
        {"index": 2, "text": "uh", "start": 9700, "end": 14500},
    ]
    assert merge_runs(found, 100) == [
        {"start": 0, "end": 14500, "indexes": [0, 1, 2]}]


def test_merge_runs_mixed():
    found = [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 1, "text": "mm", "start": 4850, "end": 9650},
        {"index": 3, "text": "uh", "start": 9700, "end": 14500},
    ]
    assert merge_runs(found, 100) == [
        {"start": 0, "end": 9650, "indexes": [0, 1]},
        {"start": 9700, "end": 14500, "indexes": [3]}]


def test_merge_runs_negative_gap_raises_value_error():
    with pytest.raises(ValueError, match="max_gap"):
        merge_runs([], -1)


def test_merge_runs_does_not_mutate_found():
    found = [
        {"index": 0, "text": "öö", "start": 0, "end": 4800},
        {"index": 1, "text": "mm", "start": 4850, "end": 9650},
    ]
    before = [dict(f) for f in found]
    merge_runs(found, 100)
    assert found == before
