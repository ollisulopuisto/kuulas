"""Next-episode name computation, logic only (WP66).

Pure Python, stdlib only (re). No imports from kuulas, plain ValueError
errors, no user-facing text.
"""

import pytest

from kuulas.next_episode import next_name, parse_episode


def test_next_name_s13e04():
    assert next_name("s13e04") == "s13e05"


def test_next_name_vikasietotila():
    assert next_name("Vikasietotila s13e09") == "Vikasietotila s13e10"


def test_next_name_episode_99_width_growth():
    assert next_name("Episode 99") == "Episode 100"


def test_next_name_ep007():
    assert next_name("ep007") == "ep008"


def test_next_name_date_is_not_the_last_number():
    assert next_name("2026-10-15 show 4") == "2026-10-15 show 5"


def test_next_name_suffix_is_kept():
    assert next_name("show 4 litteroitu") == "show 5 litteroitu"


def test_next_name_last_number_in_the_whole_name_wins():
    # "show 4 v2" -> "show 4 v3": the last number ("2") is bumped, not "4".
    assert next_name("show 4 v2") == "show 4 v3"


def test_next_name_only_digits():
    assert next_name("007") == "008"


def test_next_name_zero_padding_preserved_on_rollover():
    assert next_name("ep009") == "ep010"


def test_next_name_no_digit_raises():
    with pytest.raises(ValueError, match="number"):
        next_name("no numbers here")


def test_next_name_empty_raises():
    with pytest.raises(ValueError, match="number"):
        next_name("")


def test_parse_episode_s13e04():
    assert parse_episode("s13e04") == {
        "prefix": "s13e",
        "number": 4,
        "width": 2,
        "suffix": "",
    }


def test_parse_episode_with_suffix():
    assert parse_episode("show 4 litteroitu") == {
        "prefix": "show ",
        "number": 4,
        "width": 1,
        "suffix": " litteroitu",
    }


def test_parse_episode_date_not_last_number():
    assert parse_episode("2026-10-15 show 4") == {
        "prefix": "2026-10-15 show ",
        "number": 4,
        "width": 1,
        "suffix": "",
    }


def test_parse_episode_last_number_wins():
    assert parse_episode("show 4 v2") == {
        "prefix": "show 4 v",
        "number": 2,
        "width": 1,
        "suffix": "",
    }


def test_parse_episode_width_is_digit_count():
    assert parse_episode("ep007")["width"] == 3


def test_parse_episode_no_digit_raises():
    with pytest.raises(ValueError, match="number"):
        parse_episode("no numbers")


def test_next_name_agrees_with_parse_episode():
    for name in ("s13e04", "Vikasietotila s13e09", "Episode 99", "ep007",
                 "2026-10-15 show 4", "show 4 v2", "show 4 litteroitu"):
        parsed = parse_episode(name)
        expected = (
            parsed["prefix"]
            + str(parsed["number"] + 1).zfill(parsed["width"])
            + parsed["suffix"])
        assert next_name(name) == expected
