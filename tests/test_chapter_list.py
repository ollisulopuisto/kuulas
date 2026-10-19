"""A chapter list from markers, for show notes (G18).

``chapter_lines`` takes a project's markers as plain
``{"frame": int, "name": str}`` dicts (any order; ``frame`` in frames at
``rate``) plus the programme length in frames, and returns the
``"<time> <name>"`` lines show notes need: time as ``M:SS`` under an hour
and ``H:MM:SS`` from one hour on, seconds floored. Markers outside the
programme, unnamed markers and every marker after the first of its second
are dropped; a programme whose first kept marker is past the first second
starts with ``"0:00 Intro"``. ``chapter_text`` joins the lines for a text
export. The module is pure logic, stdlib only, and imports nothing from
kuulas.
"""

import copy

import pytest

from kuulas.chapter_list import chapter_lines, chapter_text

RATE = 48000


def marker(frame: int, name: str) -> dict:
    return {"frame": frame, "name": name}


# -- the time format ------------------------------------------------------------


def test_the_task_time_examples():
    markers = [
        marker(0, "Alku"),
        marker(247 * RATE, "Kesken"),
        marker(3729 * RATE, "Loppu"),
    ]
    lines = chapter_lines(markers, RATE, 3730 * RATE)
    assert lines == ["0:00 Alku", "4:07 Kesken", "1:02:09 Loppu"]


def test_seconds_are_floored():
    markers = [marker(61 * RATE + 500, "Hetki")]
    assert chapter_lines(markers, RATE, 62 * RATE) == ["0:00 Intro", "1:01 Hetki"]


def test_the_one_hour_boundary():
    under = chapter_lines([marker(35990, "Melkein")], 10, 36500)
    on = chapter_lines([marker(36000, "Tasan")], 10, 36500)
    assert under == ["0:00 Intro", "59:59 Melkein"]
    assert on == ["0:00 Intro", "1:00:00 Tasan"]


def test_minutes_are_not_zero_padded_below_an_hour():
    five = chapter_lines([marker(5, "Vissi")], 1, 600)
    ten = chapter_lines([marker(600, "Kymppi")], 1, 3600)
    assert five == ["0:00 Intro", "0:05 Vissi"]
    assert ten == ["0:00 Intro", "10:00 Kymppi"]


def test_hours_are_not_zero_padded_and_minutes_are():
    ten_hours = chapter_lines([marker(36000, "Paske")], 1, 36001)
    assert ten_hours == ["0:00 Intro", "10:00:00 Paske"]


# -- skipping markers ------------------------------------------------------------


def test_names_are_stripped():
    markers = [marker(0, "  Alku  ")]
    assert chapter_lines(markers, RATE, RATE) == ["0:00 Alku"]


def test_unnamed_markers_are_skipped():
    markers = [
        marker(0, ""),
        marker(RATE, "   "),
        marker(2 * RATE, "Myöhäinen"),
    ]
    assert chapter_lines(markers, RATE, 3 * RATE) == [
        "0:00 Intro",
        "0:02 Myöhäinen",
    ]


def test_negative_frames_are_skipped():
    markers = [marker(-1, "Ennen"), marker(0, "Alku")]
    assert chapter_lines(markers, RATE, RATE) == ["0:00 Alku"]


def test_markers_at_or_past_the_programme_length_are_skipped():
    markers = [
        marker(RATE, "Yli"),
        marker(RATE + 100, "Pahasti yli"),
        marker(RATE - 1, "Viimeinen"),
    ]
    assert chapter_lines(markers, RATE, RATE) == ["0:00 Viimeinen"]


# -- order and one chapter per second ---------------------------------------------


def test_markers_are_sorted_by_frame():
    markers = [marker(2 * RATE, "Kolmas"), marker(0, "Ensimmäinen"),
               marker(RATE, "Toinen")]
    assert chapter_lines(markers, RATE, 3 * RATE) == [
        "0:00 Ensimmäinen",
        "0:01 Toinen",
        "0:02 Kolmas",
    ]


def test_two_markers_in_the_same_second_keep_the_smaller_frame():
    # The larger frame comes first in the input; the smaller frame still wins.
    markers = [marker(72000, "Myöhempi"), marker(RATE, "Aiempi")]
    assert chapter_lines(markers, RATE, 2 * RATE) == ["0:00 Intro", "0:01 Aiempi"]


def test_equal_frames_keep_the_earlier_input():
    markers = [marker(RATE, "Ensimmäinen"), marker(RATE, "Toinen")]
    assert chapter_lines(markers, RATE, 2 * RATE) == [
        "0:00 Intro",
        "0:01 Ensimmäinen",
    ]


# -- the Intro line ----------------------------------------------------------------


def test_a_first_kept_marker_at_second_zero_gives_no_intro():
    at_zero = chapter_lines([marker(0, "Alku"), marker(2 * RATE, "Loppu")],
                            RATE, 3 * RATE)
    near_zero = chapter_lines([marker(100, "Alku")], RATE, RATE)
    same_second = chapter_lines([marker(1000, "Myöhempi"), marker(0, "Alku")],
                                RATE, RATE)
    assert at_zero == ["0:00 Alku", "0:02 Loppu"]
    assert near_zero == ["0:00 Alku"]
    assert same_second == ["0:00 Alku"]


def test_a_first_kept_marker_past_second_zero_adds_the_intro():
    markers = [marker(RATE, "Alku")]
    assert chapter_lines(markers, RATE, 2 * RATE) == ["0:00 Intro", "0:01 Alku"]


def test_a_skipped_marker_does_not_hold_the_first_second():
    # The unnamed marker at frame 0 is skipped, so the first KEPT marker is
    # at second 1 and the Intro line is added.
    markers = [marker(0, ""), marker(RATE, "Alku")]
    assert chapter_lines(markers, RATE, 2 * RATE) == ["0:00 Intro", "0:01 Alku"]


# -- empties, errors and mutation ----------------------------------------------------


def test_empty_markers_give_no_lines():
    assert chapter_lines([], RATE, RATE) == []


def test_all_markers_skipped_gives_no_lines():
    # Nothing is kept, so there is no first kept marker to compare with
    # second 0: no Intro-only list.
    markers = [marker(0, "Alku"), marker(-5, "Ennen"), marker(100, "Yli")]
    assert chapter_lines(markers, RATE, 0) == []


def test_zero_and_negative_rates_raise():
    with pytest.raises(ValueError, match="rate"):
        chapter_lines([], 0, RATE)
    with pytest.raises(ValueError, match="rate"):
        chapter_lines([], -48000, RATE)


def test_a_negative_programme_length_raises():
    with pytest.raises(ValueError, match="programme"):
        chapter_lines([marker(0, "Alku")], RATE, -1)


def test_chapter_text_joins_with_newlines():
    assert chapter_text(["0:00 Alku", "1:02:09 Loppu"]) == (
        "0:00 Alku\n1:02:09 Loppu"
    )
    assert chapter_text([]) == ""


def test_inputs_are_not_mutated():
    markers = [
        marker(2 * RATE, "  Kolmas  "),
        marker(RATE, "Toinen"),
        marker(0, "Ensimmäinen"),
    ]
    before = copy.deepcopy(markers)
    result = chapter_lines(markers, RATE, 3 * RATE)
    assert markers == before
    assert result == ["0:00 Ensimmäinen", "0:01 Toinen", "0:02 Kolmas"]
