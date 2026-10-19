"""Gain suggestions toward a target loudness.

Pure Python, stdlib only (math), no imports from kuulas. Errors are plain
ValueError; there is no user-facing text.
"""

import pytest

from kuulas.level_suggest import suggest_all, suggest_gain


def test_within_tolerance_gives_zero_gain():
    measured, target = -23.0, -24.0  # wanted = -1.0, inside tolerance 1.0
    result = suggest_gain(measured, target)
    assert result == {"gain_db": 0.0, "clamped": False, "within_tolerance": True}


def test_tolerance_boundary_counts_as_within():
    measured, target = -25.0, -24.0  # wanted = +1.0, exactly the tolerance
    result = suggest_gain(measured, target)
    assert result == {"gain_db": 0.0, "clamped": False, "within_tolerance": True}


def test_outside_tolerance_suggests_the_wanted_change():
    measured, target = -26.0, -24.0  # wanted = +2.0
    result = suggest_gain(measured, target)
    assert result == {"gain_db": 2.0, "clamped": False, "within_tolerance": False}


def test_needed_cut_is_suggested():
    measured, target = -20.0, -24.0  # wanted = -4.0
    result = suggest_gain(measured, target)
    assert result == {"gain_db": -4.0, "clamped": False, "within_tolerance": False}


def test_boost_beyond_max_boost_is_clamped():
    measured, target = -40.0, -24.0  # wanted = +16.0, limit is +12.0
    result = suggest_gain(measured, target)
    assert result == {"gain_db": 12.0, "clamped": True, "within_tolerance": False}


def test_cut_beyond_max_cut_is_clamped():
    measured, target = -10.0, -40.0  # wanted = -30.0, limit is -24.0
    result = suggest_gain(measured, target)
    assert result == {"gain_db": -24.0, "clamped": True, "within_tolerance": False}


def test_exact_limit_is_not_clamped():
    measured, target = -36.0, -24.0  # wanted = +12.0 == max_boost
    assert suggest_gain(measured, target) == {
        "gain_db": 12.0,
        "clamped": False,
        "within_tolerance": False,
    }
    measured, target = -12.0, -36.0  # wanted = -24.0 == max_cut
    assert suggest_gain(measured, target) == {
        "gain_db": -24.0,
        "clamped": False,
        "within_tolerance": False,
    }


def test_result_is_rounded_to_one_decimal():
    measured, target = -25.25, -24.0  # wanted = +1.25 -> round-half-even 1.2
    result = suggest_gain(measured, target)
    assert result["gain_db"] == 1.2
    assert result == {"gain_db": 1.2, "clamped": False, "within_tolerance": False}


def test_none_measured_means_silence():
    assert suggest_gain(None, -24.0) == {
        "gain_db": 0.0,
        "clamped": False,
        "within_tolerance": False,
    }


def test_nan_measured_means_silence():
    assert suggest_gain(float("nan"), -24.0) == {
        "gain_db": 0.0,
        "clamped": False,
        "within_tolerance": False,
    }


def test_minus_inf_measured_means_silence():
    assert suggest_gain(float("-inf"), -24.0) == {
        "gain_db": 0.0,
        "clamped": False,
        "within_tolerance": False,
    }


def test_silence_result_is_independent_of_limits():
    assert suggest_gain(None, -24.0, max_boost=5.0, max_cut=5.0) == {
        "gain_db": 0.0,
        "clamped": False,
        "within_tolerance": False,
    }


def test_negative_max_boost_raises_value_error():
    with pytest.raises(ValueError, match="max_boost"):
        suggest_gain(-26.0, -24.0, max_boost=-1.0)


def test_negative_max_cut_raises_value_error():
    with pytest.raises(ValueError, match="max_cut"):
        suggest_gain(-20.0, -24.0, max_cut=-1.0)


def test_negative_tolerance_raises_value_error():
    with pytest.raises(ValueError, match="tolerance"):
        suggest_gain(-26.0, -24.0, tolerance=-1.0)


def test_suggest_all_returns_results_keyed_by_id_in_order():
    entries = [
        {"id": "a", "measured": -23.0, "target": -24.0},
        {"id": "b", "measured": -40.0, "target": -24.0},
        {"id": "c", "measured": -20.0, "target": -24.0},
    ]
    result = suggest_all(entries)
    assert list(result) == ["a", "b", "c"]
    assert result["a"] == {"gain_db": 0.0, "clamped": False, "within_tolerance": True}
    assert result["b"] == {"gain_db": 12.0, "clamped": True, "within_tolerance": False}
    assert result["c"] == {"gain_db": -4.0, "clamped": False, "within_tolerance": False}


def test_suggest_all_uses_the_given_tolerance():
    entries = [{"id": "a", "measured": -25.0, "target": -23.0}]  # wanted = +2.0
    assert suggest_all(entries, tolerance=3.0)["a"] == {
        "gain_db": 0.0,
        "clamped": False,
        "within_tolerance": True,
    }
    assert suggest_all(entries, tolerance=1.0)["a"] == {
        "gain_db": 2.0,
        "clamped": False,
        "within_tolerance": False,
    }


def test_suggest_all_duplicate_id_raises_value_error():
    entries = [
        {"id": "a", "measured": -23.0, "target": -24.0},
        {"id": "a", "measured": -20.0, "target": -24.0},
    ]
    with pytest.raises(ValueError, match="a"):
        suggest_all(entries)


def test_suggest_all_silence_entry_gives_the_silence_dict():
    entries = [{"id": "a", "measured": None, "target": -24.0}]
    assert suggest_all(entries) == {
        "a": {"gain_db": 0.0, "clamped": False, "within_tolerance": False},
    }


def test_suggest_all_does_not_mutate_the_input():
    entries = [
        {"id": "a", "measured": -23.0, "target": -24.0},
        {"id": "b", "measured": None, "target": -24.0},
    ]
    before = [dict(entry) for entry in entries]
    suggest_all(entries)
    assert entries == before
