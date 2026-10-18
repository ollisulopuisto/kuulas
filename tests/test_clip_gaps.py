"""Gap and overlap report for one track's clips."""

import pytest

from kuulas.clip_gaps import clip_gaps


def test_empty_list_is_empty_report():
    assert clip_gaps([]) == {"gaps": [], "overlaps": []}


def test_single_clip_is_empty_report():
    assert clip_gaps([(0, 10)]) == {"gaps": [], "overlaps": []}


def test_touching_clips_give_neither():
    assert clip_gaps([(0, 10), (10, 20)]) == {"gaps": [], "overlaps": []}


def test_gap_between_clips():
    assert clip_gaps([(0, 10), (20, 30)]) == {
        "gaps": [(10, 20)],
        "overlaps": [],
    }


def test_overlap_between_clips():
    assert clip_gaps([(0, 20), (5, 30)]) == {
        "gaps": [],
        "overlaps": [(5, 20)],
    }


def test_unsorted_input_is_sorted_by_time():
    assert clip_gaps([(20, 30), (0, 10)]) == {
        "gaps": [(10, 20)],
        "overlaps": [],
    }


def test_contained_clips_do_not_extend_the_running_end():
    assert clip_gaps([(0, 30), (5, 10)]) == {
        "gaps": [],
        "overlaps": [(5, 10)],
    }


def test_mixed_gaps_and_overlaps_in_one_pass():
    assert clip_gaps([(0, 10), (5, 15), (20, 30)]) == {
        "gaps": [(15, 20)],
        "overlaps": [(5, 10)],
    }


def test_multiple_gaps_and_overlaps():
    assert clip_gaps([(0, 5), (10, 15), (12, 20), (30, 40)]) == {
        "gaps": [(5, 10), (20, 30)],
        "overlaps": [(12, 15)],
    }


def test_input_is_not_mutated():
    clips = [(20, 30), (0, 10)]
    before = list(clips)
    clip_gaps(clips)
    assert clips == before


def test_end_not_greater_than_start_raises_value_error():
    with pytest.raises(ValueError, match="clip end 5 is not greater than start 5"):
        clip_gaps([(5, 5)])
    with pytest.raises(ValueError, match="clip end 5 is not greater than start 10"):
        clip_gaps([(10, 5)])
