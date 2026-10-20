"""Tests for automixer flags file parsing (T67)."""

import pytest

from kuulas.automix_flags import parse_flags


def test_example_lines():
    text = (
        "1:41.6\u20131:45.9  Tuukka  block +8.0 dB off its level, gain -8.0 dB\n"
        "4:12.6\u20134:32.7  Aame  block -10.7 dB off its level, gain +6.0 dB\n"
        "2:45.0\u20132:46.6  Tuukka  loud +7.5 dB over its block (not changed)\n"
        "10:57.2\u201311:05.1  Olli  block +7.1 dB off its level, gain -7.1 dB\n"
    )
    flags, bad_lines = parse_flags(text)
    assert bad_lines == []
    assert len(flags) == 4

    assert flags[0] == {
        "start_s": pytest.approx(101.6),
        "end_s": pytest.approx(105.9),
        "name": "Tuukka",
        "kind": "block",
        "off_db": 8.0,
        "gain_db": -8.0,
    }
    assert flags[1] == {
        "start_s": pytest.approx(252.6),
        "end_s": pytest.approx(272.7),
        "name": "Aame",
        "kind": "block",
        "off_db": -10.7,
        "gain_db": 6.0,
    }
    assert flags[2] == {
        "start_s": pytest.approx(165.0),
        "end_s": pytest.approx(166.6),
        "name": "Tuukka",
        "kind": "loud",
        "off_db": 7.5,
        "gain_db": None,
    }
    assert flags[3] == {
        "start_s": pytest.approx(657.2),
        "end_s": pytest.approx(665.1),
        "name": "Olli",
        "kind": "block",
        "off_db": 7.1,
        "gain_db": -7.1,
    }


def test_hour_time():
    text = "1:02:03.5\u20131:02:10.0  Tuukka  block +8.0 dB off its level, gain -8.0 dB\n"
    flags, bad_lines = parse_flags(text)
    assert bad_lines == []
    assert len(flags) == 1
    assert flags[0]["start_s"] == pytest.approx(3723.5)
    assert flags[0]["end_s"] == pytest.approx(3730.0)


def test_name_with_space_and_digits():
    text = (
        "1:41.6\u20131:45.9  Anna Maria  block +8.0 dB off its level, gain -8.0 dB\n"
        "2:45.0\u20132:46.6  Speaker 2  loud +7.5 dB over its block\n"
    )
    flags, bad_lines = parse_flags(text)
    assert bad_lines == []
    assert len(flags) == 2
    assert flags[0]["name"] == "Anna Maria"
    assert flags[1]["name"] == "Speaker 2"


def test_hyphen_separator():
    text = "1:41.6-1:45.9  Tuukka  block +8.0 dB off its level, gain -8.0 dB\n"
    flags, bad_lines = parse_flags(text)
    assert bad_lines == []
    assert len(flags) == 1
    assert flags[0]["name"] == "Tuukka"


def test_blank_lines_skipped():
    text = (
        "\n"
        "   \n"
        "1:41.6\u20131:45.9  Tuukka  block +8.0 dB off its level, gain -8.0 dB\n"
        "\n"
        "  \t \n"
        "2:45.0\u20132:46.6  Tuukka  loud +7.5 dB over its block (not changed)\n"
        "\n"
    )
    flags, bad_lines = parse_flags(text)
    assert bad_lines == []
    assert len(flags) == 2


def test_garbage_lines():
    text = (
        "1:41.6\u20131:45.9  Tuukka  block +8.0 dB off its level, gain -8.0 dB\n"
        "This is an invalid header\n"
        "2:45.0\u20132:46.6  Tuukka  loud +7.5 dB over its block (not changed)\n"
        "Another corrupt line without times\n"
    )
    flags, bad_lines = parse_flags(text)
    assert len(flags) == 2
    assert bad_lines == [
        (2, "This is an invalid header"),
        (4, "Another corrupt line without times"),
    ]


def test_empty_string_and_invalid_input():
    assert parse_flags("") == ([], [])
    assert parse_flags("   \n\t\n") == ([], [])
    assert parse_flags(None) == ([], [])  # type: ignore[arg-type]


def test_windows_line_endings():
    text = (
        "1:41.6\u20131:45.9  Tuukka  block +8.0 dB off its level, gain -8.0 dB\r\n"
        "4:12.6\u20134:32.7  Aame  block -10.7 dB off its level, gain +6.0 dB\r\n"
    )
    flags, bad_lines = parse_flags(text)
    assert bad_lines == []
    assert len(flags) == 2
    assert flags[0]["name"] == "Tuukka"
    assert flags[1]["name"] == "Aame"
