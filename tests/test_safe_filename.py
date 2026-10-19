"""A safe file name for an export (G19).

``safe_filename`` turns any proposed name into one that macOS, Windows
and Linux accept: the characters ``/ \\ : * ? " < > |`` and the control
characters below code 32 become ``-``, runs of whitespace become one
space, leading and trailing spaces and dots are stripped, an empty
result becomes ``untitled``, a Windows-reserved base name gets a ``_``
prefix, and the name fits ``max_len`` characters, keeping its last
extension when the base must be cut. Finnish letters and emoji stay. The
module is pure logic, stdlib only, and imports nothing from kuulas.
"""

import pytest

from kuulas.safe_filename import safe_filename

# -- characters -----------------------------------------------------------------


def test_the_characters_the_systems_refuse_become_dashes():
    assert safe_filename('a/b\\c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"


def test_control_characters_below_32_become_dashes():
    assert safe_filename("a\x01b\x1fc") == "a-b-c"


def test_tabs_and_newlines_are_controls_not_whitespace():
    # The control replacement runs before the whitespace collapse, so a
    # tab (code 9) becomes "-", not a space.
    assert safe_filename("a\tb\nc") == "a-b-c"


def test_control_means_code_below_32_so_del_stays():
    # The rule is "code below 32": DEL (code 127) is above it and stays.
    assert safe_filename("a\x7fb") == "a\x7fb"


def test_whitespace_runs_become_one_space():
    assert safe_filename("a  b   c") == "a b c"


def test_unicode_spaces_collapse_to_one_ascii_space():
    assert safe_filename("a\xa0\xa0 b") == "a b"
    assert safe_filename("a\u2003b") == "a b"


def test_finnish_letters_and_emoji_stay():
    name = "Äänite össä 🎙️.flac"
    assert safe_filename(name) == name


def test_leading_and_trailing_spaces_and_dots_are_stripped():
    assert safe_filename("  ..name..  ") == "name"
    assert safe_filename(".hidden") == "hidden"
    assert safe_filename("name.") == "name"


def test_an_empty_result_becomes_untitled():
    assert safe_filename("") == "untitled"
    assert safe_filename("...") == "untitled"
    assert safe_filename("   ") == "untitled"


# -- the Windows reserved base names ----------------------------------------------


def test_windows_reserved_names_get_an_underscore_prefix():
    assert safe_filename("CON") == "_CON"
    assert safe_filename("nul") == "_nul"
    assert safe_filename("Prn") == "_Prn"
    assert safe_filename("aux.wav") == "_aux.wav"
    assert safe_filename("COM3") == "_COM3"
    assert safe_filename("lpt9.tar.gz") == "_lpt9.tar.gz"


def test_reserved_is_the_part_before_the_first_dot():
    # Windows reserves the stem whatever follows the first dot.
    assert safe_filename("con.txt.bak") == "_con.txt.bak"
    assert safe_filename("COM1.5") == "_COM1.5"
    # A trailing dot is stripped first, so this is still "con".
    assert safe_filename("con.") == "_con"


def test_near_misses_are_not_reserved():
    assert safe_filename("console") == "console"
    assert safe_filename("com10") == "com10"
    assert safe_filename("con t") == "con t"


# -- the length and the extension --------------------------------------------------


def test_a_long_name_is_cut_to_max_len():
    assert safe_filename("a" * 200) == "a" * 120


def test_the_last_extension_is_kept_when_cutting():
    # ".gz" is the last extension; ".tar" is part of the cut base.
    assert safe_filename("a" * 200 + ".tar.gz") == "a" * 117 + ".gz"


def test_the_extension_is_one_to_five_ascii_letters_or_digits():
    assert safe_filename("b" * 200 + ".a") == "b" * 118 + ".a"
    assert safe_filename("b" * 200 + ".mp3") == "b" * 116 + ".mp3"
    assert safe_filename("b" * 200 + ".abcde") == "b" * 114 + ".abcde"
    # Six characters is not an extension by the rule; nor is a non-ASCII
    # letter: both are cut with the base.
    assert safe_filename("b" * 200 + ".abcdef") == "b" * 120
    assert safe_filename("b" * 200 + ".ä") == "b" * 120


def test_a_cut_never_leaves_a_trailing_space_or_dot():
    # The cut would land right after the space; the name must not end
    # with one, or a second pass would strip it again.
    assert safe_filename("Episode 42, the apple tree", 8) == "Episode"
    assert safe_filename("abcd fg.wav", 9) == "abcd.wav"


def test_the_cut_and_the_reserved_prefix_settle():
    # A cut can turn a base into a reserved word: "control.webm" fits to
    # "con.webm", which then gets the prefix and is fitted again.
    assert safe_filename("control.webm", 8) == "_co.webm"
    # The prefix can push a fitted name over max_len: fitted again.
    assert safe_filename("con.armature", 8) == "_co.arma"


def test_the_result_is_never_longer_than_max_len():
    for name in ("abcdefghij", "control.webm", "con.armature",
                 "Episode 42, the apple tree", "xyz.abcde"):
        assert len(safe_filename(name, 8)) <= 8


# -- errors ------------------------------------------------------------------------


def test_max_len_below_8_raises():
    with pytest.raises(ValueError, match="max_len"):
        safe_filename("name", 7)
    with pytest.raises(ValueError, match="max_len"):
        safe_filename("name", 0)
    with pytest.raises(ValueError, match="max_len"):
        safe_filename("name", -1)
    assert safe_filename("name", 8) == "name"


def test_a_non_string_name_raises():
    for name in (42, None, b"name", ["name"]):
        with pytest.raises(ValueError, match="string"):
            safe_filename(name)


# -- idempotency and mutation --------------------------------------------------------


def test_idempotent_on_several_inputs():
    cases = (
        ("control.webm", 8),
        ("con.armature", 8),
        ("abcdefg hij", 8),
        ("  ..what/../..  ", 120),
        ("a\tb\x01c  d   .WAV", 120),
        ("NUL", 8),
        ("com1.tar.gz", 8),
        ("x.abcdefg", 8),
        ("xyz.abcde", 8),
        ("", 120),
        ("...", 120),
        (" \t\t ", 120),
        ("Äänite össä 🎙️.wav", 120),
        ("a.b.cdefg", 8),
        ("CON", 8),
    )
    for name, max_len in cases:
        once = safe_filename(name, max_len)
        assert safe_filename(once, max_len) == once, (name, once)


def test_the_input_is_not_mutated():
    name = "abc/def .wav"
    safe_filename(name)
    assert name == "abc/def .wav"
