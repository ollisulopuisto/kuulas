"""Merging and subtracting frame ranges."""

import pytest

from kuulas.range_ops import merge_ranges, subtract_ranges, total_length


def test_merge_ranges_empty_gives_empty_list():
    assert merge_ranges([]) == []


def test_merge_ranges_single_range_is_returned_as_is():
    assert merge_ranges([(3, 7)]) == [(3, 7)]


def test_merge_ranges_returns_a_sorted_list():
    assert merge_ranges([(10, 15), (0, 5)]) == [(0, 5), (10, 15)]


def test_merge_ranges_overlapping_ranges_join():
    assert merge_ranges([(0, 10), (5, 15)]) == [(0, 15)]


def test_merge_ranges_touching_ranges_join_with_default_gap():
    assert merge_ranges([(0, 10), (10, 20)]) == [(0, 20)]


def test_merge_ranges_separate_ranges_stay_separate_with_default_gap():
    assert merge_ranges([(0, 5), (10, 15)]) == [(0, 5), (10, 15)]


def test_merge_ranges_gap_joins_ranges_within_the_gap():
    assert merge_ranges([(0, 5), (7, 10)], gap=2) == [(0, 10)]


def test_merge_ranges_gap_one_leaves_a_one_frame_gap_separate():
    assert merge_ranges([(0, 5), (7, 10)], gap=1) == [(0, 5), (7, 10)]


def test_merge_ranges_contained_range_is_absorbed():
    assert merge_ranges([(0, 20), (5, 10), (12, 18)]) == [(0, 20)]


def test_merge_ranges_negative_gap_raises_value_error():
    with pytest.raises(ValueError, match="gap"):
        merge_ranges([(0, 5)], gap=-1)


def test_merge_ranges_end_not_greater_than_start_raises_value_error():
    with pytest.raises(ValueError, match="end"):
        merge_ranges([(5, 5)])
    with pytest.raises(ValueError, match="end"):
        merge_ranges([(5, 3)])


def test_merge_ranges_does_not_mutate_the_input():
    ranges = [(10, 15), (0, 5)]
    before = list(ranges)
    merge_ranges(ranges)
    assert ranges == before


def test_subtract_ranges_with_no_holes_returns_merged_ranges():
    assert subtract_ranges([(10, 15), (0, 5)], []) == [(0, 5), (10, 15)]


def test_subtract_ranges_hole_in_the_middle_splits_the_range():
    assert subtract_ranges([(0, 20)], [(5, 10)]) == [(0, 5), (10, 20)]


def test_subtract_ranges_hole_covering_everything_gives_nothing():
    assert subtract_ranges([(0, 20)], [(0, 20)]) == []


def test_subtract_ranges_hole_at_the_start_trims_the_range():
    assert subtract_ranges([(0, 10)], [(0, 5)]) == [(5, 10)]


def test_subtract_ranges_hole_at_the_end_trims_the_range():
    assert subtract_ranges([(0, 10)], [(5, 10)]) == [(0, 5)]


def test_subtract_ranges_hole_outside_the_range_changes_nothing():
    assert subtract_ranges([(10, 20)], [(0, 5)]) == [(10, 20)]
    assert subtract_ranges([(10, 20)], [(20, 30)]) == [(10, 20)]


def test_subtract_ranges_multiple_holes_and_ranges():
    assert subtract_ranges([(0, 10), (20, 30)], [(3, 7), (25, 28)]) == [
        (0, 3),
        (7, 10),
        (20, 25),
        (28, 30),
    ]


def test_subtract_ranges_overlapping_holes_are_merged_first():
    assert subtract_ranges([(0, 20)], [(5, 10), (8, 12)]) == [(0, 5), (12, 20)]


def test_subtract_ranges_overlapping_ranges_are_merged_first():
    assert subtract_ranges([(0, 10), (5, 15)], [(7, 8)]) == [(0, 7), (8, 15)]


def test_subtract_ranges_no_empty_pieces():
    assert subtract_ranges([(0, 10)], [(0, 10)]) == []
    assert subtract_ranges([(0, 10)], [(5, 10)]) == [(0, 5)]


def test_subtract_ranges_end_not_greater_than_start_raises_value_error():
    with pytest.raises(ValueError, match="end"):
        subtract_ranges([(5, 5)], [])
    with pytest.raises(ValueError, match="end"):
        subtract_ranges([], [(5, 5)])


def test_subtract_ranges_does_not_mutate_the_inputs():
    ranges = [(0, 20)]
    holes = [(5, 10)]
    before_ranges, before_holes = list(ranges), list(holes)
    subtract_ranges(ranges, holes)
    assert ranges == before_ranges
    assert holes == before_holes


def test_total_length_sums_merged_ranges():
    assert total_length([(0, 5), (10, 15)]) == 10


def test_total_length_counts_overlaps_only_once():
    assert total_length([(0, 10), (5, 15)]) == 15


def test_total_length_of_empty_is_zero():
    assert total_length([]) == 0


def test_total_length_end_not_greater_than_start_raises_value_error():
    with pytest.raises(ValueError, match="end"):
        total_length([(5, 3)])
