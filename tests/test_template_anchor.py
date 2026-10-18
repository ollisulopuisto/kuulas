"""Anchor resolution for standing clips in a series template."""

import pytest

from kuulas.template_anchor import resolve_anchor, validate_anchor


def test_validate_anchor_start_keeps_offset():
    assert validate_anchor({"from": "start", "offset": 5.0}) == {
        "from": "start",
        "offset": 5.0,
    }


def test_validate_anchor_start_defaults_offset_to_zero_float():
    assert validate_anchor({"from": "start"}) == {"from": "start", "offset": 0.0}


def test_validate_anchor_end_keeps_negative_offset():
    assert validate_anchor({"from": "end", "offset": -3.5}) == {
        "from": "end",
        "offset": -3.5,
    }


def test_validate_anchor_marker_with_name_and_offset():
    assert validate_anchor(
        {"from": "marker", "name": "intro", "offset": -2.0}
    ) == {"from": "marker", "name": "intro", "offset": -2.0}


def test_validate_anchor_marker_without_name_raises():
    with pytest.raises(ValueError, match="name"):
        validate_anchor({"from": "marker", "offset": 0.0})


def test_validate_anchor_marker_with_empty_name_raises():
    with pytest.raises(ValueError, match="name"):
        validate_anchor({"from": "marker", "name": "", "offset": 0.0})


def test_validate_anchor_unknown_from_raises():
    with pytest.raises(ValueError, match="from"):
        validate_anchor({"from": "middle", "offset": 0.0})


def test_validate_anchor_returns_a_copy_and_does_not_mutate_input():
    anchor = {"from": "start"}
    before = dict(anchor)
    result = validate_anchor(anchor)
    assert result is not anchor
    assert anchor == before
    assert result == {"from": "start", "offset": 0.0}


def test_resolve_anchor_from_start_at_zero():
    assert resolve_anchor({"from": "start"}, 10.0, 60.0, {}, 48000) == 0


def test_resolve_anchor_from_start_at_offset_seconds():
    # 2.5 s at 48000 Hz
    assert resolve_anchor(
        {"from": "start", "offset": 2.5}, 10.0, 60.0, {}, 48000
    ) == 120000


def test_resolve_anchor_from_end_clip_ends_at_programme_end():
    assert resolve_anchor(
        {"from": "end", "offset": 0.0}, 10.0, 60.0, {}, 48000
    ) == 2400000


def test_resolve_anchor_from_end_offset_before_end():
    # clip end is 5 s before the programme end: start = 60 - 10 - 5 = 45 s
    assert resolve_anchor(
        {"from": "end", "offset": 5.0}, 10.0, 60.0, {}, 48000
    ) == 2160000


def test_resolve_anchor_from_end_clamped_at_zero():
    # 60 - 60 - 5 = -5 s -> clamped to 0
    assert resolve_anchor(
        {"from": "end", "offset": 5.0}, 60.0, 60.0, {}, 48000
    ) == 0


def test_resolve_anchor_from_marker():
    markers = {"intro": 30.0}
    assert resolve_anchor(
        {"from": "marker", "name": "intro"}, 10.0, 60.0, markers, 48000
    ) == 1440000


def test_resolve_anchor_from_marker_with_negative_offset():
    markers = {"intro": 30.0}
    # 30 - 2 = 28 s
    assert resolve_anchor(
        {"from": "marker", "name": "intro", "offset": -2.0},
        10.0, 60.0, markers, 48000,
    ) == 1344000


def test_resolve_anchor_from_marker_clamped_at_zero():
    markers = {"intro": 1.0}
    # 1 - 5 = -4 s -> clamped to 0
    assert resolve_anchor(
        {"from": "marker", "name": "intro", "offset": -5.0},
        10.0, 60.0, markers, 48000,
    ) == 0


def test_resolve_anchor_unknown_marker_raises():
    with pytest.raises(ValueError, match="marker"):
        resolve_anchor(
            {"from": "marker", "name": "missing"}, 10.0, 60.0, {}, 48000
        )


def test_resolve_anchor_unknown_from_raises():
    with pytest.raises(ValueError, match="from"):
        resolve_anchor(
            {"from": "middle"}, 10.0, 60.0, {}, 48000
        )


def test_resolve_anchor_non_positive_rate_raises():
    with pytest.raises(ValueError, match="rate"):
        resolve_anchor({"from": "start"}, 10.0, 60.0, {}, 0)
    with pytest.raises(ValueError, match="rate"):
        resolve_anchor({"from": "start"}, 10.0, 60.0, {}, -48000)


def test_resolve_anchor_negative_clip_length_raises():
    with pytest.raises(ValueError, match="clip_length"):
        resolve_anchor({"from": "start"}, -1.0, 60.0, {}, 48000)


def test_resolve_anchor_negative_programme_length_raises():
    with pytest.raises(ValueError, match="programme_length"):
        resolve_anchor({"from": "start"}, 10.0, -1.0, {}, 48000)


def test_resolve_anchor_inputs_not_mutated():
    anchor = {"from": "marker", "name": "intro"}
    markers = {"intro": 30.0}
    before_anchor = dict(anchor)
    before_markers = dict(markers)
    resolve_anchor(anchor, 10.0, 60.0, markers, 48000)
    assert anchor == before_anchor
    assert markers == before_markers
