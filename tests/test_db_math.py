"""Decibel arithmetic helpers: db_to_gain, gain_to_db, sum_db, mean_db, clamp_db.

Pure Python, stdlib only, no imports from kuulas. Errors are plain
ValueError; there is no user-facing text.
"""

import math

import pytest

from kuulas.db_math import clamp_db, db_to_gain, gain_to_db, mean_db, sum_db


def test_db_to_gain_zero_is_unity():
    assert db_to_gain(0.0) == 1.0


def test_db_to_gain_converts_known_values():
    assert db_to_gain(6.020599913279624) == pytest.approx(2.0)
    assert db_to_gain(-6.020599913279624) == pytest.approx(0.5)


def test_db_to_gain_minus_inf_is_silence():
    assert db_to_gain(float("-inf")) == 0.0


def test_db_to_gain_nan_raises_value_error():
    with pytest.raises(ValueError, match="db"):
        db_to_gain(float("nan"))


def test_gain_to_db_unity_is_zero():
    assert gain_to_db(1.0) == 0.0


def test_gain_to_db_converts_known_values():
    assert gain_to_db(2.0) == pytest.approx(6.020599913279624)
    assert gain_to_db(0.5) == pytest.approx(-6.020599913279624)


def test_gain_to_db_zero_and_negative_use_the_floor():
    assert gain_to_db(0.0) == -120.0
    assert gain_to_db(-1.0) == -120.0


def test_gain_to_db_uses_a_custom_floor():
    assert gain_to_db(0.0, floor_db=-60.0) == -60.0
    assert gain_to_db(0.001, floor_db=-60.0) == pytest.approx(-60.0)


def test_gain_to_db_nan_raises_value_error():
    with pytest.raises(ValueError, match="gain"):
        gain_to_db(float("nan"))


def test_sum_db_empty_is_minus_inf():
    assert sum_db([]) == float("-inf")


def test_sum_db_single_level_passes_through():
    assert sum_db([0.0]) == 0.0
    assert sum_db([-6.020599913279624]) == pytest.approx(-6.020599913279624)


def test_sum_db_adds_power():
    assert sum_db([0.0, 0.0]) == pytest.approx(10.0 * math.log10(2.0))
    assert sum_db([0.0, 0.0, 0.0]) == pytest.approx(10.0 * math.log10(3.0))


def test_sum_db_minus_inf_levels_are_silence():
    assert sum_db([float("-inf"), float("-inf")]) == float("-inf")
    assert sum_db([0.0, float("-inf")]) == 0.0


def test_sum_db_nan_raises_value_error():
    with pytest.raises(ValueError, match="levels"):
        sum_db([0.0, float("nan")])


def test_mean_db_empty_is_minus_inf():
    assert mean_db([]) == float("-inf")


def test_mean_db_single_level_passes_through():
    assert mean_db([0.0]) == 0.0
    assert mean_db([-6.0]) == -6.0


def test_mean_db_is_power_mean():
    levels = [0.0, 6.020599913279624]
    assert mean_db(levels) == pytest.approx(sum_db(levels) - 10.0 * math.log10(2.0))
    assert mean_db([0.0, 0.0]) == 0.0
    assert mean_db([-6.020599913279624, -6.020599913279624]) == pytest.approx(
        -6.020599913279624
    )


def test_mean_db_minus_inf_levels_are_silence():
    assert mean_db([float("-inf"), float("-inf")]) == float("-inf")


def test_mean_db_nan_raises_value_error():
    with pytest.raises(ValueError, match="levels"):
        mean_db([0.0, float("nan")])


def test_clamp_db_clamps_into_the_interval():
    assert clamp_db(5.0, 0.0, 10.0) == 5.0
    assert clamp_db(-5.0, 0.0, 10.0) == 0.0
    assert clamp_db(15.0, 0.0, 10.0) == 10.0


def test_clamp_db_lo_greater_than_hi_raises_value_error():
    with pytest.raises(ValueError, match="lo"):
        clamp_db(5.0, 10.0, 0.0)


def test_clamp_db_nan_raises_value_error():
    with pytest.raises(ValueError, match="db"):
        clamp_db(float("nan"), 0.0, 10.0)
