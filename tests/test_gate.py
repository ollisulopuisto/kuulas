"""The pure gate range arithmetic (WP44's merge core): one merged gate per
track instead of thousands of clip pieces."""

import itertools

import numpy as np

from kuulas.gate import (
    add_range,
    merge_ranges,
    normalise,
    ranges_from_mask,
    remove_range,
    ripple,
)

RATE = 48_000
HOP = 480  # frames per mask step: 10 ms at 48 kHz, as analysis.hop_frames


def test_normalise_sorts_drops_and_merges():
    # unsorted input, one empty, one reversed, one touching pair
    ranges = [(30, 40), (0, 5), (5, 5), (7, 3), (10, 20), (20, 25)]

    assert normalise(ranges) == ((0, 5), (10, 25), (30, 40))


def test_normalise_merges_overlaps_into_one():
    assert normalise([(20, 30), (0, 100), (40, 50)]) == ((0, 100),)
    assert normalise([]) == ()


def test_merge_ranges_closes_gaps_shorter_than_min_open():
    assert merge_ranges([(0, 100), (130, 200)], 40, 1) == ((0, 200),)
    # a gap of exactly min_open frames stays open
    assert merge_ranges([(0, 100), (130, 200)], 30, 1) == ((0, 100), (130, 200))


def test_merge_ranges_drops_ranges_shorter_than_min_closed():
    assert merge_ranges([(0, 100), (500, 520)], 1, 30) == ((0, 100),)
    # a range of exactly min_closed frames stays
    assert merge_ranges([(500, 530)], 1, 30) == ((500, 530),)


def test_merge_ranges_closes_before_it_drops():
    # Two 20-frame pieces with a 5-frame gap: closing first bridges them
    # into one 45-frame range, which then clears min_closed 30. Dropping
    # first would lose both pieces; WP44 pins the order.
    assert merge_ranges([(0, 20), (25, 45)], 40, 30) == ((0, 45),)


def test_merge_ranges_without_thresholds_is_normalise():
    raw = [(30, 40), (0, 5), (10, 20), (20, 25)]

    assert merge_ranges(raw, 0, 0) == normalise(raw)


def test_ranges_from_mask_marks_closed_runs_as_frame_ranges():
    mask = np.array([False, True, True, False, False, True])

    assert ranges_from_mask(mask, HOP) == ((HOP, 3 * HOP), (5 * HOP, 6 * HOP))


def test_ranges_from_mask_corners():
    assert ranges_from_mask(np.array([], dtype=bool), HOP) == ()
    assert ranges_from_mask(np.ones(5, dtype=bool), HOP) == ((0, 5 * HOP),)
    # runs that end at the mask's edge end there, not a step later
    assert ranges_from_mask(np.array([True, True, False, True]), 10) == (
        (0, 20), (30, 40))


def test_add_range_inserts_merges_and_bridges():
    assert add_range(((0, 50),), 100, 200) == ((0, 50), (100, 200))
    assert add_range(((0, 50),), 50, 100) == ((0, 100),)
    assert add_range(((0, 10), (20, 30)), 8, 22) == ((0, 30),)
    assert add_range(((0, 100),), 40, 60) == ((0, 100),)


def test_add_range_of_an_empty_span_changes_nothing():
    assert add_range(((0, 50),), 60, 60) == ((0, 50),)


def test_remove_range_from_the_middle_of_a_range_gives_two():
    assert remove_range(((0, 100),), 40, 60) == ((0, 40), (60, 100))


def test_remove_range_trims_covers_and_leaves_untouched():
    assert remove_range(((0, 100),), 0, 100) == ()
    assert remove_range(((0, 20), (100, 200)), 10, 190) == ((0, 10), (190, 200))
    assert remove_range(((50, 150),), 100, 200) == ((50, 100),)
    assert remove_range(((150, 250),), 100, 200) == ((200, 250),)
    # touching the span's edges is not overlapping: both ranges stay whole
    assert remove_range(((0, 100), (200, 300)), 100, 200) == ((0, 100), (200, 300))


def test_remove_range_of_an_empty_span_changes_nothing():
    assert remove_range(((0, 100),), 40, 40) == ((0, 100),)


def test_ripple_shifts_the_ranges_after_the_cut():
    assert ripple(((1000, 2000),), 100, 200) == ((900, 1900),)
    assert ripple(((0, 50),), 100, 200) == ((0, 50),)


def test_ripple_deletes_the_ranges_inside_the_cut():
    assert ripple(((100, 150), (160, 200)), 100, 200) == ()


def test_ripple_trims_the_ranges_overlapping_the_cut():
    assert ripple(((50, 150),), 100, 200) == ((50, 100),)
    assert ripple(((150, 250),), 100, 200) == ((100, 150),)
    # a range covering the whole cut closes up over it
    assert ripple(((0, 300),), 100, 200) == ((0, 200),)


def test_ripple_merges_ranges_that_now_touch():
    # the range after the cut lands exactly where the range before it ends
    assert ripple(((0, 100), (200, 300)), 100, 200) == ((0, 200),)


def test_ripple_of_an_empty_cut_changes_nothing():
    assert ripple(((10, 20),), 100, 100) == ((10, 20),)


def test_a_one_hour_mask_merges_to_under_a_tenth():
    # The WP44 fixture: a synthetic hour whose gate toggles every 0.1 to
    # 0.3 s (10 to 30 hops at 10 ms), as a fine Auto-Silence measurement
    # leaves thousands of closed stretches behind.
    steps = RATE * 3600 // HOP
    rng = np.random.default_rng(20261017)
    durations = rng.integers(10, 31, size=18_500)
    mask = np.repeat(np.tile((True, False), 9_250), durations)[:steps]

    raw = ranges_from_mask(mask, HOP)
    assert len(raw) > 1_000  # thousands of raw ranges

    min_open, min_closed = round(0.4 * RATE), round(0.3 * RATE)
    merged = merge_ranges(raw, min_open, min_closed)

    assert 10 * len(merged) < len(raw)  # far fewer: under one tenth
    assert merged == normalise(merged)  # the merged gate is a proper gate
    # the two steps hold in the output: every range clears min_closed and
    # every gap between ranges clears min_open (the drop runs last, and it
    # can only widen a gap)
    assert all(end - start >= min_closed for start, end in merged)
    assert all(next_start - end >= min_open
               for (_, end), (next_start, _) in itertools.pairwise(merged))
