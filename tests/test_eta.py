"""Estimate the time left of a long job."""

from kuulas.eta import EtaSampler, format_remaining, remaining_parts, remaining_seconds


def test_sampler_keeps_only_growing_fractions():
    s = EtaSampler()
    s.add(0, 0.1)
    s.add(30, 0.4)
    s.add(60, 0.4)  # stands still -> ignored
    s.add(90, 0.3)  # goes down -> ignored
    assert s.samples() == [(0, 0.1), (30, 0.4)]


def test_sampler_ignores_fractions_outside_zero_to_one():
    s = EtaSampler()
    s.add(0, -0.1)
    s.add(10, 1.5)
    s.add(20, 0.5)
    assert s.samples() == [(20, 0.5)]


def test_sampler_ignores_backwards_times():
    s = EtaSampler()
    s.add(30, 0.4)
    s.add(0, 0.1)  # time goes backwards -> ignored
    assert s.samples() == [(30, 0.4)]


def test_sampler_caps_at_200_samples():
    s = EtaSampler()
    for i in range(250):
        s.add(float(i), i / 250.0)
    kept = s.samples()
    assert len(kept) == 200
    assert kept[0] == (50.0, 0.2)
    assert kept[-1] == (249.0, 0.996)


def test_sampler_estimate_matches_remaining_seconds():
    s = EtaSampler()
    for t, f in [(0, 0.1), (30, 0.4), (60, 0.7)]:
        s.add(t, f)
    assert s.estimate() == remaining_seconds(s.samples())


def test_sampler_samples_returns_a_copy():
    s = EtaSampler()
    s.add(0, 0.1)
    s.add(30, 0.4)
    out = s.samples()
    out.append((999, 9.9))
    assert s.samples() == [(0, 0.1), (30, 0.4)]


def test_remaining_parts_none():
    assert remaining_parts(None) is None


def test_remaining_parts_under_a_minute():
    assert remaining_parts(0) == ("under_minute", 0)
    assert remaining_parts(59) == ("under_minute", 0)


def test_remaining_parts_minutes():
    assert remaining_parts(60) == ("minutes", 1)
    assert remaining_parts(119) == ("minutes", 2)
    assert remaining_parts(5400) == ("minutes", 90)


def test_remaining_parts_hours_minutes():
    assert remaining_parts(3600) == ("minutes", 60)
    assert remaining_parts(5401) == ("hours_minutes", (1, 30))
    assert remaining_parts(7500) == ("hours_minutes", (2, 5))


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


def test_samples_further_apart_than_the_windows_still_give_an_estimate():
    """The automixer's bar moves in jumps minutes apart: the 30 s and 60 s windows
    then hold only the newest sample, and that must not mean 'stuck' or 'done'."""
    samples = [(0.0, 0.0), (120.0, 0.25), (240.0, 0.5)]
    assert remaining_seconds(samples) == 240


def test_a_bar_that_has_not_moved_for_a_while_is_stuck_even_with_sparse_samples():
    samples = [(0.0, 0.0), (120.0, 0.5), (240.0, 0.5)]
    assert remaining_seconds(samples) is None
