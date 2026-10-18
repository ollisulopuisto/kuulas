"""Fades per speaker from a fade plan."""

import pytest

from kuulas.fade_apply import fade_lengths, fades_per_speaker


def crossfade() -> dict:
    return {
        "from": "A",
        "to": "B",
        "kind": "crossfade",
        "out_start": 1.0,
        "out_end": 1.5,
        "in_start": 1.0,
        "in_end": 1.5,
    }


def cut() -> dict:
    return {
        "from": "A",
        "to": "B",
        "kind": "cut",
        "out_start": 10.0,
        "out_end": 10.06,
        "in_start": 9.94,
        "in_end": 10.0,
    }


def overlap() -> dict:
    return {
        "from": "A",
        "to": "B",
        "kind": "overlap",
        "out_start": None,
        "out_end": None,
        "in_start": None,
        "in_end": None,
    }


def test_empty_plan_gives_empty_dict():
    assert fades_per_speaker([]) == {}


def test_overlap_entry_gives_no_fades():
    assert fades_per_speaker([overlap()]) == {}


def test_crossfade_gives_out_for_from_and_in_for_to():
    plan = [crossfade()]
    result = fades_per_speaker(plan)
    assert result == {
        "A": [{"side": "out", "start": 1.0, "end": 1.5}],
        "B": [{"side": "in", "start": 1.0, "end": 1.5}],
    }


def test_cut_gives_out_for_from_and_in_for_to():
    plan = [cut()]
    result = fades_per_speaker(plan)
    assert result == {
        "A": [{"side": "out", "start": 10.0, "end": 10.06}],
        "B": [{"side": "in", "start": 9.94, "end": 10.0}],
    }


def test_same_speaker_accumulates_and_is_sorted_by_start():
    plan = [
        {"from": "A", "to": "B", "kind": "cut", "out_start": 10.0, "out_end": 10.06,
         "in_start": 9.94, "in_end": 10.0},
        {"from": "C", "to": "A", "kind": "crossfade", "out_start": 5.0, "out_end": 5.5,
         "in_start": 5.0, "in_end": 5.5},
    ]
    result = fades_per_speaker(plan)
    assert result["A"] == [
        {"side": "in", "start": 5.0, "end": 5.5},
        {"side": "out", "start": 10.0, "end": 10.06},
    ]
    assert result["C"] == [{"side": "out", "start": 5.0, "end": 5.5}]
    assert result["B"] == [{"side": "in", "start": 9.94, "end": 10.0}]


def test_fade_with_end_not_after_start_is_skipped():
    plan = [
        {"from": "A", "to": "B", "kind": "cut", "out_start": 2.0, "out_end": 1.5,
         "in_start": 9.94, "in_end": 10.0},
        crossfade(),
    ]
    result = fades_per_speaker(plan)
    assert result == {
        "A": [{"side": "out", "start": 1.0, "end": 1.5}],
        "B": [
            {"side": "in", "start": 1.0, "end": 1.5},
            {"side": "in", "start": 9.94, "end": 10.0},
        ],
    }


def test_unknown_kind_raises_value_error():
    plan = [dict(crossfade(), kind="weird")]
    with pytest.raises(ValueError, match="kind"):
        fades_per_speaker(plan)


def test_input_is_not_mutated():
    plan = [crossfade()]
    before = [dict(entry) for entry in plan]
    fades_per_speaker(plan)
    assert plan == before


def test_fade_lengths_converts_times_to_frames():
    fades = [{"side": "out", "start": 1.0, "end": 1.5}]
    result = fade_lengths(fades, 48000)
    assert result == [{"side": "out", "start": 48000, "end": 72000, "length": 24000}]


def test_fade_lengths_is_at_least_one_frame():
    fades = [{"side": "in", "start": 0.0, "end": 0.00001}]
    result = fade_lengths(fades, 48000)
    assert result == [{"side": "in", "start": 0, "end": 0, "length": 1}]


def test_fade_lengths_bad_rate_raises_value_error():
    with pytest.raises(ValueError, match="rate"):
        fade_lengths([{"side": "out", "start": 0.0, "end": 1.0}], 0)


def test_fade_lengths_negative_rate_raises_value_error():
    with pytest.raises(ValueError, match="rate"):
        fade_lengths([{"side": "out", "start": 0.0, "end": 1.0}], -48000)


def test_fade_lengths_input_not_mutated():
    fades = [{"side": "out", "start": 1.0, "end": 1.5}]
    before = [dict(fade) for fade in fades]
    fade_lengths(fades, 48000)
    assert fades == before
