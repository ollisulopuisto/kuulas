"""A few matched windows are not permission to move audio."""

import math

import pytest

from kuulas.align_proposal import propose


def points(offset=2.345, drift=.0001):
    return [(5 + 10*i, offset + drift*(5 + 10*i), 2.) for i in range(12)]


def test_robust_proposal_requires_independent_support_and_covers_the_recording():
    samples = points()
    samples[4] = (45., 100., 9.)
    result = propose(samples)
    assert result is not None
    assert result.offset == pytest.approx(2.345, abs=.001)
    assert result.slope == pytest.approx(.0001, abs=.00001)
    assert len(result.support) == 11
    assert result.excluded == (4,)


def test_a_step_is_not_mistaken_for_clock_drift():
    samples = [(t, lag + (1.2 if t > 60 else 0), q) for t, lag, q in points()]
    assert propose(samples) is None


def test_two_competing_offsets_and_excessive_drift_are_not_proposals():
    assert propose([(t, lag + (2 if i % 2 else 0), q)
                    for i, (t, lag, q) in enumerate(points())]) is None
    assert propose(points(drift=.01)) is None


def test_duplicate_overlapping_windows_and_short_coverage_do_not_count_as_support():
    assert propose([(5., 2., 3.)] * 12) is None
    assert propose([(5. + i/10, 2., 3.) for i in range(12)]) is None
    assert propose(points()[:2]) is None


def test_unclear_and_nonfinite_points_cannot_win_a_fit():
    assert propose([(t, lag, 1.4) for t, lag, q in points()]) is None
    assert propose([(math.nan, 0., 3.), *points()]) is None
    assert propose([(0., math.inf, 3.), *points()]) is None


def test_negative_offset_and_clock_slope_are_preserved():
    result = propose(list(reversed(points(-10, -.0002))))
    assert result.offset == pytest.approx(-10)
    assert result.slope == pytest.approx(-.0002)
