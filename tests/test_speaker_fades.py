"""Where to crossfade between two speakers: plan_fades.

Pure Python, stdlib only, no imports from kuulas. Errors are plain
ValueError; there is no user-facing text. Inputs are never mutated.
"""

import pytest

from kuulas.speaker_fades import plan_fades


def turn(speaker, start, end):
    return {"speaker": speaker, "s": start, "e": end}


def entry(from_, to, kind, out_start, out_end, in_start, in_end):
    return {"from": from_, "to": to, "kind": kind,
            "out_start": pytest.approx(out_start),
            "out_end": pytest.approx(out_end),
            "in_start": pytest.approx(in_start),
            "in_end": pytest.approx(in_end)}


def overlap_entry(from_, to):
    return {"from": from_, "to": to, "kind": "overlap",
            "out_start": None, "out_end": None,
            "in_start": None, "in_end": None}


def test_empty_list_gives_no_fades():
    assert plan_fades([]) == []


def test_single_turn_gives_no_fades():
    assert plan_fades([turn("A", 0, 10)]) == []


def test_same_speaker_neighbours_give_no_entry():
    assert plan_fades([turn("A", 0, 10), turn("A", 11, 20)]) == []


def test_talk_over_is_overlap_with_no_fades():
    assert plan_fades([turn("A", 0, 10), turn("B", 9, 20)]) == [
        overlap_entry("A", "B")]


def test_gap_exactly_zero_is_crossfade_at_the_point():
    assert plan_fades([turn("A", 0, 10), turn("B", 10, 20)], long_gap=0.5,
                      fade=0.12) == [
        entry("A", "B", "crossfade", 10.0, 10.0, 10.0, 10.0)]


def test_crossfade_window_centred_on_midpoint():
    assert plan_fades([turn("A", 0, 10), turn("B", 10.4, 20)], long_gap=0.5,
                      fade=0.12) == [
        entry("A", "B", "crossfade", 10.14, 10.26, 10.14, 10.26)]


def test_crossfade_gap_shorter_than_fade_is_the_whole_gap():
    assert plan_fades([turn("A", 0, 10), turn("B", 10.05, 20)], long_gap=0.5,
                      fade=0.12) == [
        entry("A", "B", "crossfade", 10.0, 10.05, 10.0, 10.05)]


def test_gap_exactly_long_gap_is_crossfade():
    assert plan_fades([turn("A", 0, 10), turn("B", 10.5, 20)], long_gap=0.5,
                      fade=0.12) == [
        entry("A", "B", "crossfade", 10.19, 10.31, 10.19, 10.31)]


def test_cut_when_gap_is_longer_than_long_gap():
    assert plan_fades([turn("A", 0, 10), turn("B", 11, 20)], long_gap=0.5,
                      fade=0.12) == [
        entry("A", "B", "cut", 10.0, 10.06, 10.94, 11.0)]


def test_only_different_speaker_boundaries_get_entries():
    assert plan_fades([turn("A", 0, 5), turn("A", 6, 11), turn("B", 12, 20),
                       turn("B", 21, 30), turn("C", 31, 40)], long_gap=0.5,
                      fade=0.12) == [
        entry("A", "B", "cut", 11.0, 11.06, 11.94, 12.0),
        entry("B", "C", "cut", 30.0, 30.06, 30.94, 31.0),
    ]


def test_entries_are_in_boundary_order():
    result = plan_fades([turn("A", 0, 5), turn("B", 10, 15), turn("C", 20, 25)],
                        long_gap=0.5, fade=0.12)
    assert result[0]["from"] == "A"
    assert result[0]["to"] == "B"
    assert result[1]["from"] == "B"
    assert result[1]["to"] == "C"


def test_default_long_gap_and_fade():
    assert plan_fades([turn("A", 0, 5), turn("B", 1, 10)]) == [
        overlap_entry("A", "B")]


def test_fade_zero_raises_value_error():
    with pytest.raises(ValueError, match="fade"):
        plan_fades([turn("A", 0, 10), turn("B", 11, 20)], fade=0)


def test_fade_negative_raises_value_error():
    with pytest.raises(ValueError, match="fade"):
        plan_fades([turn("A", 0, 10), turn("B", 11, 20)], fade=-0.1)


def test_long_gap_negative_raises_value_error():
    with pytest.raises(ValueError, match="long_gap"):
        plan_fades([turn("A", 0, 10), turn("B", 11, 20)], long_gap=-0.1)


def test_end_before_start_raises_value_error():
    with pytest.raises(ValueError, match="end"):
        plan_fades([turn("A", 10, 5), turn("B", 11, 20)])


def test_out_of_order_turns_raise_value_error():
    with pytest.raises(ValueError, match="order"):
        plan_fades([turn("A", 10, 20), turn("B", 5, 15)])


def test_input_is_not_mutated():
    turns = [turn("A", 0, 10), turn("B", 11, 20)]
    copy = [turn("A", 0, 10), turn("B", 11, 20)]
    plan_fades(turns)
    assert turns == copy
    assert turns[0] == copy[0]
