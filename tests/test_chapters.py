"""Chapter list formatter (WP19h)."""

import json

import pytest

from kuulas import messages
from kuulas.chapters import format_chapters
from kuulas.messages import KuulasError

RATE = 48_000


def test_chapters_are_sorted_by_frame():
    result = format_chapters([(2 * RATE, "B"), (0, "A"), (RATE, "C")], RATE, "text")
    assert result == "00:00:00 A\n00:00:01 C\n00:00:02 B\n"


def test_3725_seconds_is_zero_one_two_zero_five():
    result = format_chapters([(3725 * RATE, "Title")], RATE, "text")
    assert result == "01:02:05 Title\n"


def test_json_has_version_and_chapters():
    result = format_chapters([(RATE, "One"), (2 * RATE, "Two")], RATE, "json")
    data = json.loads(result)
    assert data == {
        "version": "1.2.0",
        "chapters": [
            {"startTime": 1.0, "title": "One"},
            {"startTime": 2.0, "title": "Two"},
        ],
    }


def test_json_rounds_start_time_to_three_decimals():
    result = format_chapters([(100, "Short")], RATE, "json")
    data = json.loads(result)
    assert data["chapters"][0]["startTime"] == 0.002


def test_finnish_titles_survive_in_text():
    result = format_chapters([(0, "Äiti öljy ålppi")], RATE, "text")
    assert result == "00:00:00 Äiti öljy ålppi\n"


def test_json_keeps_finnish_letters_readable():
    result = format_chapters([(0, "Äiti")], RATE, "json")
    assert "Äiti" in result
    data = json.loads(result)
    assert data["chapters"][0]["title"] == "Äiti"


def test_empty_chapter_list_gives_empty_text():
    assert format_chapters([], RATE, "text") == ""


def test_empty_chapter_list_gives_empty_json_chapters():
    data = json.loads(format_chapters([], RATE, "json"))
    assert data == {"version": "1.2.0", "chapters": []}


def test_negative_frame_raises():
    with pytest.raises(KuulasError) as exc:
        format_chapters([(-1, "x")], RATE, "text")
    assert exc.value.key == "error.chapters.negative_frame"


def test_empty_title_raises():
    with pytest.raises(KuulasError) as exc:
        format_chapters([(0, "   ")], RATE, "text")
    assert exc.value.key == "error.chapters.empty_title"


def test_duplicate_frame_raises():
    with pytest.raises(KuulasError) as exc:
        format_chapters([(0, "A"), (0, "B")], RATE, "text")
    assert exc.value.key == "error.chapters.duplicate_frame"


def test_unknown_style_raises():
    with pytest.raises(KuulasError) as exc:
        format_chapters([(0, "A")], RATE, "csv")
    assert exc.value.key == "error.chapters.unknown_style"


def test_error_text_is_translated_to_finnish():
    messages.set_language("fi")
    try:
        with pytest.raises(KuulasError) as exc:
            format_chapters([(-1, "x")], RATE, "text")
        assert str(exc.value) == "Luku alkaa negatiivisesta kehyksestä: -1."
    finally:
        messages.set_language("en")
