"""Tests for gain_scale.total_gain_db, waveform_scale and envelope_db_at (RED).

Waveform scale from clip, track and envelope gains: the total gain in dB, the
linear scale capped at max_scale, and linear dB interpolation over an envelope.
Pure Python, stdlib only, no imports from kuulas; errors are plain ValueError.
"""

import math

import pytest

from kuulas.gain_scale import envelope_db_at, total_gain_db, waveform_scale


def test_total_gain_db_sums_all_three():
    assert total_gain_db(1.0, 2.0, 3.0) == 6.0


def test_total_gain_db_none_is_zero():
    assert total_gain_db(None, None, None) == 0.0
    assert total_gain_db(3.0, None, None) == 3.0
    assert total_gain_db(None, -2.0, None) == -2.0
    assert total_gain_db(None, None, 4.0) == 4.0


def test_total_gain_db_negative_gains():
    assert total_gain_db(-6.0, -6.0, 0.0) == -12.0


def test_total_gain_db_minus_inf_propagates():
    assert total_gain_db(-math.inf, 5.0) == -math.inf
    assert total_gain_db(None, -math.inf, None) == -math.inf
    assert total_gain_db(1.0, 2.0, -math.inf) == -math.inf


def test_total_gain_db_non_finite_raises():
    for bad in (math.nan, math.inf):
        for args in ((bad, 0.0), (0.0, bad), (0.0, 0.0, bad)):
            try:
                total_gain_db(*args)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected ValueError for {args!r}")


def test_waveform_scale_unity_is_one():
    assert waveform_scale(0.0) == 1.0


def test_waveform_scale_plus_6_db_is_about_two():
    assert waveform_scale(6.0206) == pytest.approx(2.0, abs=1e-3)


def test_waveform_scale_minus_6_db_is_about_half():
    assert waveform_scale(-6.0206) == pytest.approx(0.5, abs=1e-3)


def test_waveform_scale_minus_inf_is_zero():
    assert waveform_scale(-math.inf) == 0.0


def test_waveform_scale_capped_at_max_scale():
    assert waveform_scale(100.0) == 32.0


def test_waveform_scale_custom_max_scale():
    assert waveform_scale(60.0, max_scale=10.0) == 10.0
    assert waveform_scale(1.0, max_scale=10.0) == pytest.approx(
        10 ** (1.0 / 20), abs=1e-9)


def test_envelope_db_at_none_is_zero():
    assert envelope_db_at(None, 0) == 0.0


def test_envelope_db_at_empty_is_zero():
    assert envelope_db_at([], 100) == 0.0


def test_envelope_db_at_single_point_held_flat():
    env = [(10, -3.0)]
    assert envelope_db_at(env, 0) == -3.0
    assert envelope_db_at(env, 10) == -3.0
    assert envelope_db_at(env, 1000) == -3.0


def test_envelope_db_at_linear_interpolation():
    env = [(0, 0.0), (10, -6.0)]
    assert envelope_db_at(env, 0) == 0.0
    assert envelope_db_at(env, 5) == -3.0
    assert envelope_db_at(env, 10) == -6.0


def test_envelope_db_at_piecewise_linear():
    env = [(0, 0.0), (10, -12.0), (20, 0.0)]
    assert envelope_db_at(env, 5) == -6.0
    assert envelope_db_at(env, 15) == -6.0


def test_envelope_db_at_before_first_and_after_last():
    env = [(100, -6.0), (200, 0.0)]
    assert envelope_db_at(env, 0) == -6.0
    assert envelope_db_at(env, 99) == -6.0
    assert envelope_db_at(env, 200) == 0.0
    assert envelope_db_at(env, 999) == 0.0


def test_envelope_db_at_input_not_mutated():
    env = [(0, 0.0), (10, -6.0)]
    before = list(env)
    envelope_db_at(env, 5)
    assert env == before
