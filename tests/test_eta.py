"""Estimate the time left of a long job."""

from kuulas.eta import format_remaining, remaining_seconds


def test_steady_progress():
    # 0.1 -> 0.4 -> 0.7 over 60 s: speed 0.01/s, 0.3 left -> 30 s
    assert remaining_seconds([(0, 0.1), (30, 0.4), (60, 0.7)]) == 30


def test_stuck_bar_returns_none():
    assert remaining_seconds([(0, 0.5), (15, 0.5), (30, 0.5)]) is None


def test_early_samples_return_none():
    assert remaining_seconds([(0, 0.9), (10, 1.0)]) is None
    assert remaining_seconds([(0, 0.01), (10, 0.02), (20, 0.03)]) is None


def test_bar_going_backwards_is_ignored():
    # (20, 0.3) is below the earlier 0.6 and ignored:
    # speed 0.7/30, 0.1 left -> 4 s
    assert remaining_seconds([(0, 0.2), (10, 0.6), (20, 0.3), (30, 0.9)]) == 4


def test_finished_gives_zero():
    assert remaining_seconds([(0, 0.2), (30, 0.6), (60, 1.0)]) == 0


def test_rounding():
    # speed 0.51/60, 0.39 left -> 45.88... -> 46 s
    assert remaining_seconds([(0, 0.1), (30, 0.35), (60, 0.61)]) == 46


def test_format_remaining_none_is_empty():
    assert format_remaining(None) == ""


def test_format_remaining_under_a_minute():
    assert format_remaining(0) == "under a minute"
    assert format_remaining(59) == "under a minute"


def test_format_remaining_minutes():
    assert format_remaining(60) == "about 1 min"
    assert format_remaining(119) == "about 2 min"
    assert format_remaining(5400) == "about 90 min"


def test_format_remaining_long_job():
    assert format_remaining(3600) == "about 60 min"
    assert format_remaining(7500) == "about 2 h 5 min"
    assert format_remaining(5401) == "about 1 h 30 min"
