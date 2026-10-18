"""Peak envelope downsampling: reduce_peaks and levels_to_bars.

Pure Python, stdlib only, no imports from kuulas. Errors are plain
ValueError; there is no user-facing text.
"""

import pytest

from kuulas.peak_reduce import levels_to_bars, reduce_peaks


def test_reduce_peaks_takes_min_of_mins_and_max_of_maxes_per_group():
    peaks = [(1.0, 5.0), (2.0, 6.0), (0.0, 3.0), (4.0, 8.0)]
    assert reduce_peaks(peaks, 2) == [(1.0, 6.0), (0.0, 8.0)]


def test_reduce_peaks_reduces_a_short_last_group_too():
    peaks = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0), (9.0, 10.0)]
    assert reduce_peaks(peaks, 3) == [(1.0, 6.0), (7.0, 10.0)]


def test_reduce_peaks_factor_one_returns_an_equal_copy():
    peaks = [(1.0, 2.0), (3.0, 4.0)]
    copy = reduce_peaks(peaks, 1)
    assert copy == peaks
    assert copy is not peaks


def test_reduce_peaks_empty_list_gives_empty():
    assert reduce_peaks([], 3) == []


def test_reduce_peaks_bad_factor_raises_value_error():
    with pytest.raises(ValueError, match="factor"):
        reduce_peaks([(1.0, 2.0)], 0)
    with pytest.raises(ValueError, match="factor"):
        reduce_peaks([(1.0, 2.0)], -1)


def test_levels_to_bars_splits_into_nearly_equal_groups_earlier_larger():
    peaks = [(float(i), float(i) + 1.0) for i in range(10)]
    assert levels_to_bars(peaks, 4) == [
        (0.0, 3.0),
        (3.0, 6.0),
        (6.0, 8.0),
        (8.0, 10.0),
    ]


def test_levels_to_bars_fewer_peaks_than_bars_returns_one_bar_per_peak():
    peaks = [(1.0, 2.0), (3.0, 4.0)]
    assert levels_to_bars(peaks, 5) == [(1.0, 2.0), (3.0, 4.0)]


def test_levels_to_bars_bad_bars_raises_value_error():
    with pytest.raises(ValueError, match="bars"):
        levels_to_bars([(1.0, 2.0)], 0)
    with pytest.raises(ValueError, match="bars"):
        levels_to_bars([(1.0, 2.0)], -1)


def test_levels_to_bars_does_not_mutate_the_input():
    peaks = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    before = list(peaks)
    levels_to_bars(peaks, 2)
    assert peaks == before
