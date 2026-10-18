"""Activity edges of a track from a loudness series."""

import pytest

from kuulas.activity_edges import activity_edges, edge_frames


def test_empty_levels_give_no_stretches():
    assert activity_edges([], 1000, -40.0, 1000, 1000) == []


def test_all_levels_below_threshold_give_no_stretches():
    assert activity_edges([-60.0, -50.0], 1000, -40.0, 1000, 1000) == []


def test_single_active_level_is_one_stretch():
    assert activity_edges([-30.0], 1000, -40.0, 1000, 1000) == [
        {"start": 0, "end": 1000},
    ]


def test_level_equal_to_threshold_is_active():
    assert activity_edges([-40.0, -50.0], 1000, -40.0, 1000, 1000) == [
        {"start": 0, "end": 1000},
    ]


def test_run_shorter_than_min_active_is_excluded():
    assert activity_edges([-30.0], 1000, -40.0, 2000, 1000) == []


def test_run_exactly_min_active_is_included():
    assert activity_edges([-30.0, -30.0], 1000, -40.0, 2000, 1000) == [
        {"start": 0, "end": 2000},
    ]


def test_run_starts_at_first_level_and_ends_one_past_last():
    assert activity_edges([-30.0, -35.0, -30.0], 1000, -40.0, 1000, 1000) == [
        {"start": 0, "end": 3000},
    ]


def test_multiple_stretches_are_reported_in_order():
    assert activity_edges(
        [-30.0, -30.0, -50.0, -30.0, -30.0, -30.0], 1000, -40.0, 1000, 1000
    ) == [{"start": 0, "end": 2000}, {"start": 3000, "end": 6000}]


def test_gap_of_exactly_min_gap_keeps_stretches_separate():
    # gap between stretches is one quiet level = 1000 frames == min_gap
    assert activity_edges(
        [-30.0, -30.0, -50.0, -30.0], 1000, -40.0, 1000, 1000
    ) == [{"start": 0, "end": 2000}, {"start": 3000, "end": 4000}]


def test_gap_shorter_than_min_gap_merges_stretches():
    # two quiet levels = 2000 frames < min_gap 3000 -> merged
    assert activity_edges(
        [-30.0, -30.0, -50.0, -50.0, -30.0], 1000, -40.0, 1000, 3000
    ) == [{"start": 0, "end": 5000}]


def test_three_stretches_merge_only_the_close_pair():
    # gap 1000 < min_gap 2000 merges the first two; gap 3000 keeps the third
    assert activity_edges(
        [-30.0, -30.0, -50.0, -30.0, -30.0, -50.0, -50.0, -50.0, -30.0],
        1000, -40.0, 1000, 2000,
    ) == [{"start": 0, "end": 5000}, {"start": 8000, "end": 9000}]


def test_hop_scales_frame_numbers():
    assert activity_edges([-30.0, -30.0], 480, -40.0, 960, 960) == [
        {"start": 0, "end": 960},
    ]


def test_hop_zero_raises_value_error():
    with pytest.raises(ValueError, match="hop"):
        activity_edges([-30.0], 0, -40.0, 1000, 1000)


def test_negative_hop_raises_value_error():
    with pytest.raises(ValueError, match="hop"):
        activity_edges([-30.0], -1000, -40.0, 1000, 1000)


def test_negative_min_active_raises_value_error():
    with pytest.raises(ValueError, match="min_active"):
        activity_edges([-30.0], 1000, -40.0, -1, 1000)


def test_negative_min_gap_raises_value_error():
    with pytest.raises(ValueError, match="min_gap"):
        activity_edges([-30.0], 1000, -40.0, 1000, -1)


def test_input_is_not_mutated():
    levels = [-30.0, -50.0, -30.0]
    before = list(levels)
    activity_edges(levels, 1000, -40.0, 1000, 1000)
    assert levels == before


def test_edge_frames_returns_sorted_deduplicated_starts_and_ends():
    stretches = [
        {"start": 0, "end": 2000},
        {"start": 3000, "end": 6000},
    ]
    assert edge_frames(stretches) == [0, 2000, 3000, 6000]


def test_edge_frames_deduplicates_shared_edges():
    stretches = [
        {"start": 0, "end": 2000},
        {"start": 2000, "end": 4000},
    ]
    assert edge_frames(stretches) == [0, 2000, 4000]


def test_edge_frames_of_empty_input_is_empty():
    assert edge_frames([]) == []
