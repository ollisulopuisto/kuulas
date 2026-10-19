"""Take position: where a take lands on the timeline."""

import pytest

from kuulas.take_position import merge_position, position_fields, read_position


def test_position_fields_normal():
    assert position_fields(100, "track-1") == {
        "timeline_start": 100,
        "track_id": "track-1",
    }


def test_position_fields_negative_start_clamps_to_zero():
    assert position_fields(-5, "track-1") == {"timeline_start": 0, "track_id": "track-1"}
    assert position_fields(0, "track-1") == {"timeline_start": 0, "track_id": "track-1"}


def test_position_fields_empty_track_id_becomes_none():
    assert position_fields(100, "") == {"timeline_start": 100, "track_id": None}
    assert position_fields(3, None) == {"timeline_start": 3, "track_id": None}


def test_position_fields_rejects_non_int_start():
    with pytest.raises(ValueError, match="start_frame"):
        position_fields(1.5, "track-1")
    with pytest.raises(ValueError, match="start_frame"):
        position_fields("100", "track-1")
    with pytest.raises(ValueError, match="start_frame"):
        position_fields(None, "track-1")


def test_read_position_complete_meta():
    assert read_position({"timeline_start": 42, "track_id": "track-1"}) == {
        "start": 42,
        "track_id": "track-1",
    }


def test_read_position_empty_and_none_track_id_become_none():
    assert read_position({"timeline_start": 42, "track_id": ""}) == {
        "start": 42,
        "track_id": None,
    }
    assert read_position({"timeline_start": 42, "track_id": None}) == {
        "start": 42,
        "track_id": None,
    }


def test_read_position_returns_none_when_missing_wrong_or_negative():
    assert read_position({}) is None
    assert read_position({"track_id": "track-1"}) is None
    assert read_position({"timeline_start": 42}) == {"start": 42, "track_id": None}
    assert read_position({"timeline_start": "42", "track_id": "track-1"}) is None
    assert read_position({"timeline_start": 42, "track_id": 7}) is None
    assert read_position({"timeline_start": -1, "track_id": "track-1"}) is None


def test_read_position_tolerates_extra_keys_and_never_raises():
    meta = {"timeline_start": 9, "track_id": "track-1", "note": "x", "format": "wav"}
    assert read_position(meta) == {"start": 9, "track_id": "track-1"}
    assert read_position(None) is None
    assert read_position(["not", "a", "dict"]) is None


def test_merge_position_adds_fields_without_mutating():
    meta = {"format": "wav", "sample_rate": 48000}
    result = merge_position(meta, 100, "track-1")
    assert result == {
        "format": "wav",
        "sample_rate": 48000,
        "timeline_start": 100,
        "track_id": "track-1",
    }
    assert meta == {"format": "wav", "sample_rate": 48000}


def test_merge_position_clamps_and_converts():
    assert merge_position({}, -3, "") == {"timeline_start": 0, "track_id": None}


def test_merge_position_rejects_bad_start():
    with pytest.raises(ValueError, match="start_frame"):
        merge_position({}, 2.5, "track-1")
