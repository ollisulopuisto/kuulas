"""Tests for gap_kinds.classify_gaps (RED: written before the module)."""

from kuulas.gap_kinds import classify_gaps


def test_empty_gaps_give_empty_result():
    assert classify_gaps([], -60.0, -40.0, 100.0, 1000.0) == []


def test_below_or_at_silence_threshold_is_silence():
    gaps = [(0, 100, -70.0), (100, 200, -60.0)]
    result = classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)
    assert result == [
        {"start": 0, "end": 100, "kind": "silence"},
        {"start": 100, "end": 200, "kind": "silence"},
    ]


def test_breath_level_within_length_limits_is_breath():
    gaps = [(0, 100, -50.0), (100, 200, -40.0)]
    result = classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)
    assert result == [
        {"start": 0, "end": 100, "kind": "breath"},
        {"start": 100, "end": 200, "kind": "breath"},
    ]


def test_breath_length_at_the_limits_is_breath():
    gaps = [(0, 100, -50.0), (100, 1100, -50.0)]
    result = classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)
    assert [r["kind"] for r in result] == ["breath", "breath"]


def test_louder_than_breath_threshold_is_other():
    gaps = [(0, 500, -30.0)]
    assert classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)[0]["kind"] == "other"


def test_breath_level_too_short_is_other():
    gaps = [(0, 50, -50.0)]
    assert classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)[0]["kind"] == "other"


def test_breath_level_too_long_is_other():
    gaps = [(0, 2000, -50.0)]
    assert classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)[0]["kind"] == "other"


def test_result_is_in_input_order():
    gaps = [(500, 600, -50.0), (0, 100, -70.0), (200, 300, -30.0)]
    result = classify_gaps(gaps, -60.0, -40.0, 100.0, 1000.0)
    assert [r["kind"] for r in result] == ["breath", "silence", "other"]
    assert [r["start"] for r in result] == [500, 0, 200]


def test_breath_db_equal_to_silence_db_raises():
    try:
        classify_gaps([(0, 100, -50.0)], -50.0, -50.0, 10.0, 100.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_min_breath_greater_than_max_breath_raises():
    try:
        classify_gaps([(0, 100, -50.0)], -60.0, -40.0, 200.0, 100.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_gap_with_end_not_after_start_raises():
    try:
        classify_gaps([(0, 0, -50.0)], -60.0, -40.0, 10.0, 100.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_input_is_not_mutated():
    gaps = [(0, 100, -50.0)]
    before = list(gaps)
    classify_gaps(gaps, -60.0, -40.0, 10.0, 100.0)
    assert gaps == before
