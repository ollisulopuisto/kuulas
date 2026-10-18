"""Tests for click_events.find_clicks (RED: written before the module)."""

from kuulas.click_events import find_clicks


def test_flat_series_gives_no_clicks():
    assert find_clicks([-60.0, -60.0, -60.0], hop=1000, jump_db=20.0,
                       max_len=5, floor_db=-40.0) == []


def test_empty_series_gives_empty():
    assert find_clicks([], hop=1000, jump_db=20.0, max_len=5, floor_db=-40.0) == []


def test_single_level_gives_empty():
    assert find_clicks([-10.0], hop=1000, jump_db=20.0, max_len=5,
                       floor_db=-40.0) == []


def test_single_loud_hop_in_silence_is_found():
    # The hop just before the run is -60. The loud hop -10 exceeds it by at
    # least jump_db (20) and is above floor_db (-40), and the following -60
    # drops back below -60 + 20/2 = -50.
    assert find_clicks([-60.0, -10.0, -60.0], hop=1000, jump_db=20.0,
                       max_len=5, floor_db=-40.0) == [(1000, 2000)]


def test_loud_run_longer_than_max_len_is_not_a_click():
    assert find_clicks([-60.0, -10.0, -10.0, -10.0, -10.0, -60.0], hop=1000,
                       jump_db=20.0, max_len=3, floor_db=-40.0) == []


def test_run_of_exactly_max_len_is_a_click():
    assert find_clicks([-60.0, -10.0, -10.0, -10.0, -60.0], hop=1000,
                       jump_db=20.0, max_len=3, floor_db=-40.0) == [(1000, 4000)]


def test_loud_hop_below_floor_is_ignored():
    assert find_clicks([-60.0, -50.0, -60.0], hop=1000, jump_db=20.0,
                       max_len=5, floor_db=-40.0) == []


def test_two_separate_clicks_give_two_ranges():
    assert find_clicks([-60.0, -10.0, -60.0, -10.0, -60.0], hop=1000,
                       jump_db=20.0, max_len=5, floor_db=-40.0) == [
                           (1000, 2000), (3000, 4000)]


def test_no_drop_after_run_is_not_a_click():
    assert find_clicks([-60.0, -10.0, -10.0], hop=1000, jump_db=20.0,
                       max_len=5, floor_db=-40.0) == []


def test_bad_hop_raises():
    try:
        find_clicks([-60.0, -10.0, -60.0], hop=0, jump_db=20.0, max_len=5,
                    floor_db=-40.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for hop <= 0")


def test_bad_max_len_raises():
    try:
        find_clicks([-60.0, -10.0, -60.0], hop=1000, jump_db=20.0, max_len=0,
                    floor_db=-40.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for max_len < 1")


def test_bad_jump_db_raises():
    try:
        find_clicks([-60.0, -10.0, -60.0], hop=1000, jump_db=0.0, max_len=5,
                    floor_db=-40.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for jump_db <= 0")


def test_input_is_not_mutated():
    levels = [-60.0, -10.0, -60.0]
    before = list(levels)
    find_clicks(levels, hop=1000, jump_db=20.0, max_len=5, floor_db=-40.0)
    assert levels == before
