"""The play plan (WP18, WP26): skip lists normalised, pieces and the map
from played frames back to programme frames. Pure, no audio."""

import pytest

from kuulas.playplan import (
    PlaybackRequestError,
    PlayPlan,
    check_loop,
    check_skip,
    normalise_skip,
)


def test_ranges_are_sorted_merged_and_clipped():
    got = normalise_skip([(500, 700), (100, 200), (150, 300), (300, 320), (900, 2000)],
                         lo=50, hi=1000)
    assert got == ((100, 320), (500, 700), (900, 1000))


def test_ranges_outside_the_played_stretch_and_empty_ones_are_dropped():
    assert normalise_skip([(0, 40), (2000, 3000), (60, 60)], lo=50, hi=1000) == ()
    assert normalise_skip([], lo=0, hi=10) == ()
    assert normalise_skip(None, lo=0, hi=10) == ()


def test_a_range_running_past_the_start_is_clipped_to_it():
    assert normalise_skip([(0, 100)], lo=50, hi=1000) == ((50, 100),)


@pytest.mark.parametrize("bad", [[(5, 3)], [(1, 2, 3)], [("a", 4)], [(-1, 4)], [(1.5, 4)],
                                 [(True, 4)], "nonsense"])
def test_a_malformed_range_is_refused_with_a_translated_error(bad):
    with pytest.raises(PlaybackRequestError) as caught:
        check_skip(bad)
    assert caught.value.key == "error.engine.bad_skip"
    assert str(caught.value) != "error.engine.bad_skip"  # it has a catalog text


def test_pieces_are_the_played_stretches_and_positions_jump_the_skip():
    plan = PlayPlan(0, 1000, ((200, 500),), rate=48000, open_end=False)
    assert plan.pieces == ((0, 200), (500, 1000))
    assert plan.length(1000) == 700
    assert plan.position(0, 1000) == 0
    assert plan.position(199, 1000) == 199
    assert plan.position(200, 1000) == 500
    assert plan.position(699, 1000) == 999
    assert plan.position(700, 1000) == 1000


def test_an_open_end_follows_the_project_length():
    plan = PlayPlan(0, 1000, ((200, 500),), rate=48000, open_end=True)
    assert plan.length(1000) == 700
    assert plan.length(1500) == 1200  # the project grew while playing
    assert plan.position(1200, 1500) == 1500
    assert plan.length(400) == 200  # it shrank into the skip


def test_a_skip_covering_everything_leaves_nothing_to_play():
    plan = PlayPlan(0, 1000, ((0, 1000),), rate=48000, open_end=True)
    assert plan.pieces == ()
    assert plan.length(1000) == 0
    assert plan.position(0, 1000) == 1000


def test_crossfades_are_10_to_20_ms_and_never_longer_than_half_a_piece():
    plan = PlayPlan(0, 48000, ((10000, 20000),), rate=48000, open_end=False)
    assert plan.half_widths[0] == 0  # no fade into the first piece
    assert 10 <= 2 * plan.half_widths[1] / 48 <= 20  # milliseconds
    plan = PlayPlan(0, 48000, ((10000, 20000), (20100, 30000)), rate=48000,
                    open_end=False)
    assert plan.pieces == ((0, 10000), (20000, 20100), (30000, 48000))
    # Half of the 100-frame piece between the skips, on both of its sides.
    assert plan.half_widths[1:] == (50, 50)


# -- loops (WP50): the wrap is a backward skip ---------------------------------


def test_a_loop_plays_its_range_over_and_over_and_positions_wrap():
    plan = PlayPlan(10000, 40000, (), rate=48000, open_end=False, loop=(10000, 40000))
    assert plan.pieces == ((10000, 40000),)
    assert plan.length(10**9) > 10**12  # endless: nothing ever flushes
    assert plan.position(0, 10**9) == 10000
    assert plan.position(29999, 10**9) == 39999
    assert plan.position(30000, 10**9) == 10000  # the backward jump
    assert plan.position(30000 * 7 + 5, 10**9) == 10005


def test_the_wrap_crossfade_is_as_long_as_a_skips():
    plan = PlayPlan(10000, 40000, (), rate=48000, open_end=False, loop=(10000, 40000))
    skipping = PlayPlan(0, 48000, ((10000, 20000),), rate=48000, open_end=False)
    assert plan.wrap_half == skipping.half_widths[1]
    assert 10 <= 2 * plan.wrap_half / 48 <= 20  # milliseconds


def test_a_loop_starting_before_its_range_plays_the_lead_in_once():
    plan = PlayPlan(5000, 40000, (), rate=48000, open_end=False, loop=(10000, 40000))
    assert plan.pieces == ((5000, 40000), (10000, 40000))
    assert plan.position(35000, 10**9) == 10000  # the first wrap, after the lead-in
    assert plan.position(35000 + 30000, 10**9) == 10000


def test_a_loop_skips_the_skip_list_inside_its_range():
    plan = PlayPlan(10000, 50000, ((20000, 30000), (0, 5000)), rate=48000,
                    open_end=False, loop=(10000, 50000))
    assert plan.pieces == ((10000, 20000), (30000, 50000))
    assert plan.position(10000, 10**9) == 30000
    assert plan.position(30000, 10**9) == 10000  # one cycle is 10000 + 20000


def test_the_next_wrap_is_found_at_or_after_a_played_frame():
    plan = PlayPlan(5000, 40000, (), rate=48000, open_end=False, loop=(10000, 40000))
    assert plan.wrap_at_or_after(0) == 35000
    assert plan.wrap_at_or_after(35000) == 35000
    assert plan.wrap_at_or_after(35001) == 65000


def test_a_loop_nothing_of_which_is_left_is_refused():
    with pytest.raises(PlaybackRequestError) as caught:
        check_loop((10000, 20000), ((0, 30000),), rate=48000)
    assert caught.value.key == "error.engine.bad_loop"


@pytest.mark.parametrize("bad", [(5, 5), (9, 3), (-1, 100000), ("a", 9), (1.5, 99999),
                                 (1, 2, 3), None, (True, 99999), 7, (0, 100)])
def test_a_malformed_or_tiny_loop_is_refused_with_a_translated_error(bad):
    with pytest.raises(PlaybackRequestError) as caught:
        check_loop(bad, (), rate=48000)
    assert caught.value.key == "error.engine.bad_loop"
    assert str(caught.value) != "error.engine.bad_loop"


def test_a_good_loop_is_returned_as_a_pair_of_ints():
    assert check_loop([100, 99999], (), rate=48000) == (100, 99999)
