"""Tests for clip_overs.overs and clip_overs.max_over_db (RED: written first).

Where a waveform clips after gain: runs of consecutive peak pairs whose level
after gain passes the limit, and the largest level above full scale in dB.
Pure Python, stdlib only, no imports from kuulas; errors are plain ValueError.
"""

import math

import pytest

from kuulas.clip_overs import max_over_db, overs

_DEFAULT_LIMIT = 10 ** (-0.1 / 20)


def test_overs_empty_gives_no_runs():
    assert overs([], 0.0) == []


def test_overs_below_limit_gives_no_runs():
    # 0.9 at unity gain is below the default -0.1 dB limit (0.98855).
    assert overs([(0.9, 0.9)], 0.0) == []
    assert overs([(0.5, -0.5), (0.0, 0.1)], 0.0) == []


def test_overs_single_peak_over_limit_is_one_run():
    assert overs([(1.0, 1.0)], 0.0) == [(0, 0)]
    assert overs([(0.99, 0.99)], 0.0) == [(0, 0)]


def test_overs_consecutive_over_peaks_merge_into_one_run():
    peaks = [(1.0, 1.0), (1.0, 1.0), (0.5, 0.5), (1.0, 1.0)]
    assert overs(peaks, 0.0) == [(0, 1), (3, 3)]


def test_overs_below_limit_peaks_break_runs():
    peaks = [(1.0, 1.0), (0.5, 0.5), (1.0, 1.0)]
    assert overs(peaks, 0.0) == [(0, 0), (2, 2)]


def test_overs_negative_min_triggers_a_run():
    # abs(-1.0) == 1.0 passes the limit even though max is 0.0.
    assert overs([(-1.0, 0.0)], 0.0) == [(0, 0)]


def test_overs_peak_0_9_at_plus_3_db_is_over_the_default_limit():
    assert overs([(0.9, 0.9)], 3.0) == [(0, 0)]


def test_overs_limit_zero_allows_exactly_full_scale():
    # threshold at limit_db=0 is 1.0; 0.9*10**(3/20) = 1.271 > 1.0.
    assert overs([(0.9, 0.9)], 3.0, limit_db=0.0) == [(0, 0)]


def test_overs_limit_above_zero_raises():
    try:
        overs([(1.0, 1.0)], 0.0, limit_db=1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for limit_db > 0")


def test_overs_non_finite_gain_raises():
    for gain in (math.nan, math.inf, -math.inf):
        try:
            overs([(1.0, 1.0)], gain)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for gain {gain!r}")


def test_overs_negative_gain_brings_peaks_below_limit():
    assert overs([(1.0, 1.0)], -60.0) == []


def test_overs_input_is_not_mutated():
    peaks = [(1.0, 1.0), (0.5, 0.5)]
    before = list(peaks)
    overs(peaks, 3.0)
    assert peaks == before


def test_max_over_db_empty_is_zero():
    assert max_over_db([], 3.0) == 0.0


def test_max_over_db_nothing_over_is_zero():
    assert max_over_db([(0.9, 0.9)], 0.0) == 0.0
    assert max_over_db([(1.0, 1.0)], 0.0) == 0.0


def test_max_over_db_peak_0_9_at_plus_3_db_is_about_2_1_db():
    # 0.9 * 10**(3/20) = 1.271 -> 20*log10(1.271) = 2.084... dB
    assert max_over_db([(0.9, 0.9)], 3.0) == pytest.approx(2.085, abs=0.01)


def test_max_over_db_negative_gain_is_zero():
    assert max_over_db([(1.0, 1.0)], -60.0) == 0.0


def test_max_over_db_deep_negative_min_counts():
    assert max_over_db([(-1.0, 0.0)], 3.0) == pytest.approx(
        20 * math.log10(10 ** (3 / 20)), abs=1e-9)


def test_max_over_db_non_finite_gain_raises():
    for gain in (math.nan, math.inf, -math.inf):
        try:
            max_over_db([(1.0, 1.0)], gain)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for gain {gain!r}")


def test_max_over_db_input_is_not_mutated():
    peaks = [(1.0, 1.0)]
    before = list(peaks)
    max_over_db(peaks, 3.0)
    assert peaks == before
