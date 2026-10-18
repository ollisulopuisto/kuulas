"""Silence runs from a loudness series."""

import pytest

from kuulas.silence_runs import silence_runs


def test_empty_list_gives_no_runs():
    assert silence_runs([], 1000, -40.0, 1000) == []


def test_all_levels_above_threshold_give_no_runs():
    assert silence_runs([-30.0, -20.0], 1000, -40.0, 1000) == []


def test_single_below_threshold_level_is_a_run():
    assert silence_runs([-60.0], 1000, -40.0, 1000) == [(0, 1000)]


def test_run_spans_from_first_to_one_past_last_level():
    assert silence_runs([-60.0, -50.0, -55.0], 1000, -40.0, 1000) == [
        (0, 3000),
    ]


def test_level_equal_to_threshold_is_not_silent():
    assert silence_runs([-40.0, -60.0], 1000, -40.0, 1000) == [(1000, 2000)]


def test_run_shorter_than_min_len_is_excluded():
    assert silence_runs([-60.0], 1000, -40.0, 2000) == []


def test_run_exactly_min_len_is_included():
    assert silence_runs([-60.0, -60.0], 1000, -40.0, 2000) == [(0, 2000)]


def test_min_len_zero_includes_every_run():
    assert silence_runs([-60.0, -30.0, -60.0], 1000, -40.0, 0) == [
        (0, 1000),
        (2000, 3000),
    ]


def test_multiple_runs_are_reported_in_order():
    assert silence_runs(
        [-60.0, -60.0, -30.0, -60.0, -60.0, -60.0], 1000, -40.0, 1000
    ) == [(0, 2000), (3000, 6000)]


def test_all_levels_silent_is_one_run():
    assert silence_runs([-60.0, -70.0], 1000, -40.0, 500) == [(0, 2000)]


def test_hop_zero_raises_value_error():
    with pytest.raises(ValueError, match="hop"):
        silence_runs([-60.0], 0, -40.0, 1000)


def test_negative_hop_raises_value_error():
    with pytest.raises(ValueError, match="hop"):
        silence_runs([-60.0], -1000, -40.0, 1000)


def test_negative_min_len_raises_value_error():
    with pytest.raises(ValueError, match="min_len"):
        silence_runs([-60.0], 1000, -40.0, -1)


def test_input_is_not_mutated():
    levels = [-60.0, -30.0, -60.0]
    before = list(levels)
    silence_runs(levels, 1000, -40.0, 1000)
    assert levels == before
