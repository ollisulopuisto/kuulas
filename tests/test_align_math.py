"""Tests for alignment maths around lag measurements."""

from __future__ import annotations

import pytest

from kuulas import align_math
from kuulas.align_math import (
    clear_windows,
    fit_drift,
    has_drift,
    jumps,
    resample_ratio,
    split_point,
)


class TestClearWindows:
    def test_keeps_clear_measurements(self):
        measurements = [
            (0.0, 0.0, 2.0),
            (1.0, 0.1, 1.5),
            (2.0, 0.2, 3.0),
        ]
        assert clear_windows(measurements) == measurements

    def test_drops_unclear_measurements(self):
        measurements = [
            (0.0, 0.0, 2.0),
            (1.0, 0.1, 1.0),
            (2.0, 0.2, 1.499),
            (3.0, 0.3, 3.0),
        ]
        assert clear_windows(measurements) == [
            (0.0, 0.0, 2.0),
            (3.0, 0.3, 3.0),
        ]

    def test_default_min_ratio_is_one_point_five(self):
        assert clear_windows([(0.0, 0.0, 1.5)]) == [(0.0, 0.0, 1.5)]
        assert clear_windows([(0.0, 0.0, 1.499)]) == []

    def test_custom_min_ratio(self):
        measurements = [
            (0.0, 0.0, 2.0),
            (1.0, 0.1, 1.5),
        ]
        assert clear_windows(measurements, min_ratio=2.0) == [
            (0.0, 0.0, 2.0),
        ]


class TestFitDrift:
    def test_recovers_exact_line(self):
        # lag = 0.1 + 0.02 * time
        measurements = [
            (0.0, 0.10, 2.0),
            (10.0, 0.30, 2.0),
            (20.0, 0.50, 2.0),
            (30.0, 0.70, 2.0),
        ]
        offset, slope = fit_drift(measurements)
        assert offset == pytest.approx(0.1)
        assert slope == pytest.approx(0.02)

    def test_ignores_unclear_windows(self):
        good = [
            (0.0, 0.0, 2.0),
            (10.0, 0.2, 2.0),
            (20.0, 0.4, 2.0),
        ]
        noisy = [
            (5.0, 999.0, 1.0),
            (15.0, -999.0, 1.2),
        ]
        offset, slope = fit_drift(good + noisy)
        assert offset == pytest.approx(0.0)
        assert slope == pytest.approx(0.02)

    def test_returns_none_for_zero_clear_points(self):
        assert fit_drift([(0.0, 0.0, 1.0)]) is None

    def test_returns_none_for_one_clear_point(self):
        assert fit_drift([(0.0, 0.0, 2.0), (1.0, 0.1, 1.0)]) is None


class TestHasDrift:
    def test_six_ms_per_minute_is_detected(self):
        # 6 ms / 1 min = 0.006 / 60 s/s
        assert has_drift(0.006 / 60)

    def test_half_ms_per_ten_minutes_is_not_detected(self):
        # 0.5 ms / 10 min = 0.0005 / 600 s/s
        assert not has_drift(0.0005 / 600)

    def test_threshold_is_exclusive(self):
        threshold = 0.001 / 600
        assert not has_drift(threshold)
        assert not has_drift(-threshold)
        assert has_drift(threshold + 1e-12)
        assert has_drift(-(threshold + 1e-12))


class TestResampleRatio:
    def test_adds_slope_to_one(self):
        assert resample_ratio(0.02) == pytest.approx(1.02)
        assert resample_ratio(-0.01) == pytest.approx(0.99)


class TestJumps:
    def test_step_of_one_point_two_seconds_is_flagged_from_step_on(self):
        # First three points define the line lag = 0.01 * time.
        # The last two are stepped up by 1.2 s.
        measurements = [
            (0.0, 0.00, 2.0),
            (10.0, 0.10, 2.0),
            (20.0, 0.20, 2.0),
            (30.0, 1.30, 2.0),
            (40.0, 1.40, 2.0),
        ]
        offset, slope = fit_drift(measurements[:3])
        assert jumps(measurements, offset, slope) == (3, 4)

    def test_empty_measurements_gives_empty_jumps(self):
        assert jumps([], 0.0, 0.0) == ()

    def test_no_jumps_when_all_points_match(self):
        measurements = [
            (0.0, 0.0, 2.0),
            (10.0, 0.2, 2.0),
            (20.0, 0.4, 2.0),
        ]
        offset, slope = fit_drift(measurements)
        assert jumps(measurements, offset, slope) == ()

    def test_uses_default_tolerance_of_twenty_ms(self):
        # A 15 ms deviation should not be flagged with the default tolerance.
        measurements = [
            (0.0, 0.0, 2.0),
            (10.0, 0.215, 2.0),  # 15 ms above line lag = 0.02 * time
            (20.0, 0.4, 2.0),
        ]
        offset, slope = fit_drift(measurements)
        assert jumps(measurements, offset, slope) == ()

    def test_custom_tolerance(self):
        # Two points define the line lag = 0; the third is 15 ms above it.
        measurements = [
            (0.0, 0.0, 2.0),
            (10.0, 0.015, 2.0),
            (20.0, 0.0, 2.0),
        ]
        offset, slope = fit_drift(measurements[:1] + measurements[2:])
        assert jumps(measurements, offset, slope, tolerance=0.020) == ()
        assert jumps(measurements, offset, slope, tolerance=0.010) == (1,)

    def test_returns_indices_into_original_list(self):
        measurements = [
            (0.0, 0.0, 2.0),
            (1.0, 0.1, 1.0),  # unclear, ignored
            (2.0, 5.0, 2.0),  # jump
        ]
        assert jumps(measurements, 0.0, 0.0) == (2,)


class TestSplitPoint:
    def test_picks_lowest_level(self):
        levels = [
            (0.0, 50.0),
            (1.0, 20.0),
            (2.0, 40.0),
        ]
        assert split_point(levels, 0.0, 2.0) == 1.0

    def test_earliest_on_ties(self):
        levels = [
            (0.0, 30.0),
            (1.0, 30.0),
            (2.0, 20.0),
        ]
        assert split_point(levels, 0.0, 1.0) == 0.0

    def test_bounds_are_inclusive(self):
        levels = [
            (0.0, 10.0),
            (1.0, 20.0),
            (2.0, 30.0),
        ]
        assert split_point(levels, 0.0, 2.0) == 0.0
        assert split_point(levels, 1.0, 2.0) == 1.0

    def test_returns_none_when_no_level_in_range(self):
        levels = [
            (0.0, 10.0),
            (1.0, 20.0),
        ]
        assert split_point(levels, 2.0, 3.0) is None

    def test_empty_levels(self):
        assert split_point([], 0.0, 10.0) is None

    def test_returns_time_not_level(self):
        levels = [
            (5.0, -30.0),
            (6.0, -60.0),
        ]
        assert split_point(levels, 5.0, 6.0) == 6.0


def test_jumps_and_clear_windows_share_the_clear_threshold(monkeypatch):
    monkeypatch.setattr(align_math, "_MIN_RATIO", 3.0)
    measurements = [(0.0, 0.0, 2.0), (60.0, 1.0, 4.0), (120.0, 0.0, 5.0)]
    # With the threshold at 3, the first window is unclear and must not be
    # reported at index 0 or shift the others' indices.
    assert align_math.jumps(measurements, 0.0, 0.0) == (1,)
