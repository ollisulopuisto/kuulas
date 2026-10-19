"""File names for exported stems (G20).

``stem_names`` turns a list of track names into the file names the
tracks' stems export as: ``"<NN> <safe name>.<extension>"``, where NN is
the 1-based position zero padded to the width of the list length (at
least two digits), the name goes through ``safe_filename`` with
``max_len=100``, a track whose name is empty after stripping uses
``Track``, and the extension is lower-cased. The whole file names are
unique ignoring case: the number prefix already makes them so, and
``unique_name`` is the safeguard. The module is pure logic and imports
only ``safe_filename`` and ``unique_name``, as the task allows.
"""

import pytest

from kuulas.stem_names import stem_names

# -- the number --------------------------------------------------------------------


def test_three_tracks_give_two_digit_positions():
    assert stem_names(["Olli", "Vieras", "Musiikki"]) == [
        "01 Olli.wav",
        "02 Vieras.wav",
        "03 Musiikki.wav",
    ]


def test_a_single_track_still_gets_two_digits():
    assert stem_names(["Olli"]) == ["01 Olli.wav"]


def test_ten_tracks_keep_two_digits():
    names = [f"N{n}" for n in range(1, 11)]
    result = stem_names(names)
    assert [name.split(" ")[0] for name in result] == [f"{n:02d}" for n in range(1, 11)]
    assert result[-1] == "10 N10.wav"


def test_the_width_flips_at_100():
    # 99 tracks give "01".."99"; 100 give "001".."100".
    assert [name.split(" ")[0] for name in stem_names(["T"] * 99)][-1] == "99"
    hundred = stem_names(["T"] * 100)
    assert hundred[0] == "001 T.wav"
    assert hundred[-1] == "100 T.wav"


def test_120_tracks_give_three_digits():
    result = stem_names(["Olli"] * 120)
    assert len(result) == 120
    assert result[0] == "001 Olli.wav"
    assert result[118] == "119 Olli.wav"
    assert result[119] == "120 Olli.wav"
    # Nothing more is added: even 120 equal names stay plain "Olli.wav".
    assert all(name.endswith("Olli.wav") for name in result)
    assert len({name.casefold() for name in result}) == 120


# -- the name ----------------------------------------------------------------------


def test_a_name_empty_after_stripping_uses_track():
    assert stem_names(["", "   "]) == ["01 Track.wav", "02 Track.wav"]


def test_a_dots_only_name_is_untitled_not_track():
    # "Track" is only for a name empty after stripping; dots survive
    # stripping, so safe_filename's own fallback applies.
    assert stem_names([" .", "  ...  "]) == [
        "01 untitled.wav",
        "02 untitled.wav",
    ]


def test_names_go_through_safe_filename():
    assert stem_names(["Olli/Vieras"]) == ["01 Olli-Vieras.wav"]
    assert stem_names(["  Con  "]) == ["01 _Con.wav"]
    assert stem_names(["NUL.tar.gz"]) == ["01 _NUL.tar.gz.wav"]


def test_finnish_letters_and_emoji_stay():
    assert stem_names(["Äänite 🎙️"]) == ["01 Äänite 🎙️.wav"]


def test_a_long_name_is_cut_to_100():
    assert stem_names(["x" * 150]) == [f"01 {'x' * 100}.wav"]


# -- uniqueness --------------------------------------------------------------------


def test_two_equal_names_need_nothing_more():
    # The task's own pin: the number already makes them unique.
    assert stem_names(["Olli", "Olli"]) == ["01 Olli.wav", "02 Olli.wav"]


def test_two_equal_names_ignoring_case_need_nothing_more():
    assert stem_names(["OLLI", "olli"]) == ["01 OLLI.wav", "02 olli.wav"]


def test_the_safeguard_fires_only_when_a_part_equals_an_earlier_whole():
    # A track literally named like an earlier whole file name collides
    # with it; the suffix lands before the extension, which stays last.
    assert stem_names(["Olli", "01 Olli.wav"]) == [
        "01 Olli.wav",
        "02 01 Olli.wav 2.wav",
    ]


# -- the extension -----------------------------------------------------------------


def test_the_extension_is_lower_cased():
    assert stem_names(["Olli"], "WAV") == ["01 Olli.wav"]
    assert stem_names(["Olli"], "Flac") == ["01 Olli.flac"]
    assert stem_names(["Olli"], "m4A") == ["01 Olli.m4a"]


def test_the_extension_may_be_one_to_five_letters_or_digits():
    assert stem_names(["Olli"], "a") == ["01 Olli.a"]
    assert stem_names(["Olli"], "mp3") == ["01 Olli.mp3"]
    assert stem_names(["Olli"], "abcde") == ["01 Olli.abcde"]


def test_a_bad_extension_raises():
    for extension in (
        "",
        "abcdef",
        "wav.",
        ".wav",
        "wa v",
        "ä",
        "wävy",
        "\u017f",
        "\u212a",
    ):
        with pytest.raises(ValueError, match="extension"):
            stem_names(["Olli"], extension)


def test_a_non_string_extension_raises():
    for extension in (42, None, b"wav", ["wav"]):
        with pytest.raises(ValueError, match="string"):
            stem_names(["Olli"], extension)


def test_a_bad_extension_raises_even_for_an_empty_list():
    # The extension is a scalar argument: it is checked before the list.
    with pytest.raises(ValueError, match="extension"):
        stem_names([], "bad.")


# -- errors and the input ------------------------------------------------------------


def test_a_non_string_track_name_raises():
    for name in (42, None, b"Olli", ["Olli"]):
        with pytest.raises(ValueError, match="string"):
            stem_names([name])


def test_order_is_kept_and_the_result_matches_the_input_length():
    names = ["C", "A", "B"]
    assert stem_names(names) == ["01 C.wav", "02 A.wav", "03 B.wav"]
    assert len(stem_names(names)) == len(names)


def test_an_empty_list_gives_an_empty_list():
    assert stem_names([]) == []


def test_the_input_is_not_mutated():
    names = ["Olli", "", "  Vieras  ", "NUL"]
    before = list(names)
    result = stem_names(names)
    assert names == before
    assert result is not names
