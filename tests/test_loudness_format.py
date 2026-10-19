"""Number formats for a loudness table.

Pure Python, stdlib only (math), no imports from kuulas. Errors are plain
ValueError; there is no user-facing text — numbers and signs only, labels are
the caller's.
"""

import pytest

from kuulas.loudness_format import format_delta, format_gain, format_lufs, level_state

EN_DASH = "\u2013"


def test_format_lufs_negative_value():
    assert format_lufs(-21.3) == "-21.3"


def test_format_lufs_zero():
    assert format_lufs(0.0) == "0.0"


def test_format_lufs_never_minus_zero():
    assert format_lufs(-0.04) == "0.0"


def test_format_lufs_positive_value():
    assert format_lufs(12.0) == "12.0"
    assert format_lufs(-100.0) == "-100.0"


def test_format_lufs_none_is_en_dash():
    assert format_lufs(None) == EN_DASH


def test_format_lufs_nan_is_en_dash():
    assert format_lufs(float("nan")) == EN_DASH


def test_format_lufs_minus_inf_is_en_dash():
    assert format_lufs(float("-inf")) == EN_DASH


def test_format_gain_positive_is_signed():
    assert format_gain(2.04) == "+2.0"


def test_format_gain_negative_is_signed():
    assert format_gain(-3.0) == "-3.0"


def test_format_gain_zero_has_no_sign():
    assert format_gain(0) == "0.0"


def test_format_gain_value_rounding_to_zero_has_no_sign():
    assert format_gain(0.04) == "0.0"
    assert format_gain(-0.04) == "0.0"


def test_format_gain_small_nonzero_stays_signed():
    assert format_gain(0.05) == "+0.1"
    assert format_gain(-0.05) == "-0.1"


def test_format_gain_none_is_en_dash():
    assert format_gain(None) == EN_DASH


def test_format_gain_nan_is_en_dash():
    assert format_gain(float("nan")) == EN_DASH


def test_format_gain_minus_inf_is_en_dash():
    assert format_gain(float("-inf")) == EN_DASH


def test_format_delta_is_target_minus_measured():
    assert format_delta(-21.3, -24.0) == format_gain(-2.7)
    assert format_delta(-20.0, -24.0) == "-4.0"
    assert format_delta(-24.0, -24.0) == "0.0"


def test_format_delta_silent_measured_is_en_dash():
    assert format_delta(None, -24.0) == EN_DASH
    assert format_delta(float("nan"), -24.0) == EN_DASH
    assert format_delta(float("-inf"), -24.0) == EN_DASH


def test_level_state_silent_for_none():
    assert level_state(None, -24.0) == "silent"


def test_level_state_silent_for_nan_and_minus_inf():
    assert level_state(float("nan"), -24.0) == "silent"
    assert level_state(float("-inf"), -24.0) == "silent"


def test_level_state_ok_at_target():
    assert level_state(-24.0, -24.0) == "ok"


def test_level_state_ok_at_tolerance_boundary():
    assert level_state(-25.0, -24.0) == "ok"  # measured 1.0 below target
    assert level_state(-23.0, -24.0) == "ok"  # measured 1.0 above target


def test_level_state_low_when_measured_is_below_target():
    assert level_state(-26.0, -24.0) == "low"


def test_level_state_high_when_measured_is_above_target():
    assert level_state(-22.0, -24.0) == "high"


def test_level_state_with_zero_tolerance_only_exact_is_ok():
    assert level_state(-24.0, -24.0, tolerance=0.0) == "ok"
    assert level_state(-24.5, -24.0, tolerance=0.0) == "low"


def test_level_state_negative_tolerance_raises_value_error():
    with pytest.raises(ValueError, match="tolerance"):
        level_state(-24.0, -24.0, tolerance=-0.5)
