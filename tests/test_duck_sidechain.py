import numpy as np

from kuulas.duck_sidechain import curve_points, gain_curve_db


def test_silence_has_no_reduction_and_simplifies_to_endpoints():
    trigger = np.zeros(20_000)
    curve = gain_curve_db(trigger, 1000)
    points = curve_points(trigger, 1000)

    assert np.all(curve == 0)
    assert points == [(0, 0.0), (19_999, 0.0)]


def test_steady_burst_follows_the_automixer_law():
    trigger = np.full(1000, 10 ** (-20 / 20))
    curve = gain_curve_db(trigger, 1000, attack_s=0.01, release_s=0.01)

    assert np.isclose(curve[500], -8.75, atol=0.02)


def test_attack_is_fast_and_release_is_slow():
    trigger = np.r_[np.zeros(100), np.full(400, 1.0), np.zeros(500)]
    curve = gain_curve_db(trigger, 1000, threshold_db=-20, ratio=2,
                          window_s=0.01, attack_s=0.02, release_s=0.2)

    assert curve[110] < -5
    assert curve[140] < -8
    assert curve[510] < -8.5
    assert abs(curve[700]) < abs(curve[510]) * 0.5
    assert curve[-1] > -1.0


def test_floor_clamps_reduction():
    trigger = np.full(100, 100.0)
    curve = gain_curve_db(trigger, 1000, threshold_db=-80, ratio=20,
                          attack_s=0.001, release_s=0.001, floor_db=-12)

    assert curve.min() == -12
    assert np.all(curve >= -12)
    assert np.all(curve <= 0)


def test_curve_points_are_deterministic_and_within_error_bound():
    rate = 100
    trigger = np.zeros(6000)
    trigger[1000:2200] = 10 ** (-20 / 20)
    trigger[4000:5000] = 10 ** (-24 / 20)
    kwargs = {"threshold_db": -30, "attack_s": 0.05, "release_s": 0.3}
    full = gain_curve_db(trigger, rate, **kwargs)
    points = curve_points(trigger, rate, max_error_db=0.3, **kwargs)
    second = curve_points(trigger, rate, max_error_db=0.3, **kwargs)
    estimate = np.interp(np.arange(len(full)), [p[0] for p in points],
                         [p[1] for p in points])

    assert points == second
    assert np.max(np.abs(full - estimate)) <= 0.3
    assert points[0][0] == 0
    assert points[-1][0] == len(full) - 1


def test_long_smooth_signal_is_reduced_to_a_sane_point_count():
    rate = 100
    seconds = 45 * 60
    time = np.arange(seconds * rate) / rate
    trigger = np.where((time % 7) < 3, 10 ** (-20 / 20), 0.0)

    points = curve_points(trigger, rate, max_error_db=0.3)

    assert len(points) < 5000

