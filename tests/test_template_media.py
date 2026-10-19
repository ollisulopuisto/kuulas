"""Matching a template's recording names against a folder's files (WP66).

``match_media`` takes the file names a template's clips name their
recordings by (``wanted``) and the file names a folder holds
(``available``, names only, no paths), and reports which wanted name found
which available name — the same name ignoring case, accents (NFKD,
combining marks dropped) and surrounding whitespace, or the same stem with
any audio extension — and which wanted names are missing. The module is
pure logic, stdlib only, and imports nothing from kuulas.
"""

import pytest

from kuulas.template_media import match_media

AUDIO_EXTENSIONS = ("wav", "flac", "mp3", "m4a", "aif", "aiff", "ogg", "opus")


# -- the whole-name match -----------------------------------------------------


def test_the_same_name_is_found():
    result = match_media(["jingle.wav"], ["intro.wav", "jingle.wav", "outro.wav"])
    assert result == {"found": {"jingle.wav": "jingle.wav"}, "missing": []}


def test_case_is_ignored():
    result = match_media(["Jingle.WAV"], ["jingle.wav"])
    assert result == {"found": {"Jingle.WAV": "jingle.wav"}, "missing": []}


def test_accents_are_ignored_in_both_directions():
    accented_available = match_media(["Aani.wav"], ["aani\u0308.wav"])
    accented_wanted = match_media(["a\u00e4ni.wav"], ["Aani.wav"])
    assert accented_available == {
        "found": {"Aani.wav": "aani\u0308.wav"},
        "missing": [],
    }
    assert accented_wanted == {"found": {"a\u00e4ni.wav": "Aani.wav"}, "missing": []}


def test_surrounding_whitespace_is_ignored():
    result = match_media(["\tjingle.wav\n"], [" jingle.wav"])
    assert result == {"found": {"\tjingle.wav\n": " jingle.wav"}, "missing": []}


def test_inner_whitespace_is_not_collapsed():
    result = match_media(["my file.wav"], ["my  file.wav", "myfile.wav"])
    assert result == {"found": {}, "missing": ["my file.wav"]}


def test_the_whole_name_matches_whatever_the_extension():
    result = match_media(["notes.txt"], ["notes.txt"])
    assert result == {"found": {"notes.txt": "notes.txt"}, "missing": []}


# -- the stem match -----------------------------------------------------------


def test_the_stem_matches_any_audio_extension():
    # The task's own example: "jingle.wav" finds "Jingle.flac".
    example = match_media(["jingle.wav"], ["Jingle.flac"])
    assert example == {"found": {"jingle.wav": "Jingle.flac"}, "missing": []}
    for ext in AUDIO_EXTENSIONS:
        result = match_media(["jingle.wav"], [f"jingle.{ext}"])
        assert result["found"] == {"jingle.wav": f"jingle.{ext}"}


def test_an_uppercase_audio_extension_matches():
    result = match_media(["jingle"], ["jingle.WAV"])
    assert result == {"found": {"jingle": "jingle.WAV"}, "missing": []}


def test_a_non_audio_extension_does_not_match():
    result = match_media(["jingle.wav"], ["jingle.txt", "jingle.mp4"])
    assert result == {"found": {}, "missing": ["jingle.wav"]}


def test_an_available_name_without_an_extension_is_not_a_stem_match():
    result = match_media(["jingle.wav"], ["jingle"])
    assert result == {"found": {}, "missing": ["jingle.wav"]}


def test_only_the_last_extension_is_dropped_from_the_stem():
    found = match_media(["part.a.wav"], ["part.a.flac"])
    missed = match_media(["part.a.wav"], ["part.flac"])
    assert found == {"found": {"part.a.wav": "part.a.flac"}, "missing": []}
    assert missed == {"found": {}, "missing": ["part.a.wav"]}


def test_a_wanted_name_without_an_extension_matches_an_audio_file():
    result = match_media(["jingle"], ["jingle.wav"])
    assert result == {"found": {"jingle": "jingle.wav"}, "missing": []}


# -- preference among several matches -----------------------------------------


def test_the_exact_case_candidate_is_preferred_whatever_its_position():
    late = match_media(["Jingle.wav"], ["jingle.wav", "Jingle.wav"])
    early = match_media(["Jingle.wav"], ["Jingle.wav", "jingle.wav"])
    assert late["found"] == {"Jingle.wav": "Jingle.wav"}
    assert early["found"] == {"Jingle.wav": "Jingle.wav"}


def test_without_an_exact_case_match_the_first_in_available_order_wins():
    whole = match_media(["JINGLE.wav"], ["jingle.wav", "Jingle.WAV"])
    stem = match_media(["JINGLE.wav"], ["Jingle.flac", "jingle.MP3"])
    assert whole["found"] == {"JINGLE.wav": "jingle.wav"}
    assert stem["found"] == {"JINGLE.wav": "Jingle.flac"}


def test_the_exact_case_stem_is_preferred():
    result = match_media(["jingle.wav"], ["Jingle.flac", "jingle.flac"])
    assert result == {"found": {"jingle.wav": "jingle.flac"}, "missing": []}


def test_the_whole_name_beats_a_stem_match():
    result = match_media(["jingle.wav"], ["jingle.flac", "jingle.wav"])
    assert result == {"found": {"jingle.wav": "jingle.wav"}, "missing": []}


# -- duplicates and order ------------------------------------------------------


def test_wanted_duplicates_give_one_found_key():
    result = match_media(["a.wav", "a.wav"], ["a.wav"])
    assert result == {"found": {"a.wav": "a.wav"}, "missing": []}


def test_wanted_duplicates_are_listed_once_in_missing():
    result = match_media(["a.wav", "a.wav"], [])
    assert result == {"found": {}, "missing": ["a.wav"]}


def test_case_variant_duplicates_collapse_to_the_first_spelling():
    found = match_media(["A.wav", "a.wav"], ["a.wav"])
    missing = match_media(["A.wav", "a.wav"], [])
    assert found == {"found": {"A.wav": "a.wav"}, "missing": []}
    assert missing == {"found": {}, "missing": ["A.wav"]}


def test_missing_order_follows_wanted():
    result = match_media(["b.wav", "a.wav", "c.wav", "a.wav"], ["c.wav"])
    assert result == {"found": {"c.wav": "c.wav"}, "missing": ["b.wav", "a.wav"]}


def test_two_wanted_names_may_find_the_same_available_name():
    result = match_media(["jingle.wav", "jingle.mp3"], ["jingle.flac"])
    assert result == {
        "found": {"jingle.wav": "jingle.flac", "jingle.mp3": "jingle.flac"},
        "missing": [],
    }


# -- errors, empties and mutation ----------------------------------------------


def test_a_non_string_name_raises_value_error():
    with pytest.raises(ValueError, match="must be a string"):
        match_media(["jingle.wav", 5], ["jingle.wav"])
    with pytest.raises(ValueError, match="must be a string"):
        match_media(["jingle.wav"], ["jingle.wav", None])


def test_empty_wanted_and_empty_available():
    assert match_media([], []) == {"found": {}, "missing": []}
    assert match_media(["a.wav"], []) == {"found": {}, "missing": ["a.wav"]}


def test_inputs_are_not_mutated():
    wanted = ["Jingle.wav", "  intro.flac ", "jingle.wav"]
    available = ["jingle.wav", " Intro.FLAC ", "notes.txt"]
    wanted_before, available_before = list(wanted), list(available)
    result = match_media(wanted, available)
    assert wanted == wanted_before
    assert available == available_before
    assert result == {
        "found": {"Jingle.wav": "jingle.wav", "  intro.flac ": " Intro.FLAC "},
        "missing": [],
    }
