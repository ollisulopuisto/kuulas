"""Talk time per speaker: talk_share.

Pure Python, stdlib only, no imports from kuulas. Errors are plain
ValueError; there is no user-facing text. Inputs are never mutated.
"""

import pytest

from kuulas.talk_share import talk_share


def test_empty_dict_gives_zeros_and_empty_dicts():
    assert talk_share({}) == {
        "per_speaker": {},
        "total": 0,
        "overlap": 0,
        "share": {},
    }


def test_single_speaker_single_range():
    result = talk_share({"A": [(0, 100)]})
    assert result == {
        "per_speaker": {"A": 100},
        "total": 100,
        "overlap": 0,
        "share": {"A": 1.0},
    }


def test_two_disjoint_speakers():
    result = talk_share({"A": [(0, 50)], "B": [(100, 200)]})
    assert result["per_speaker"] == {"A": 50, "B": 100}
    assert result["total"] == 150
    assert result["overlap"] == 0
    assert result["share"] == {"A": pytest.approx(1 / 3), "B": pytest.approx(2 / 3)}


def test_two_overlapping_speakers():
    result = talk_share({"A": [(0, 100)], "B": [(50, 150)]})
    assert result["per_speaker"] == {"A": 100, "B": 100}
    assert result["total"] == 150
    assert result["overlap"] == 50
    assert result["share"] == {"A": 0.5, "B": 0.5}


def test_one_speaker_overlapping_ranges_are_merged():
    result = talk_share({"A": [(0, 100), (50, 150), (200, 250)]})
    assert result["per_speaker"] == {"A": 200}
    assert result["total"] == 200
    assert result["overlap"] == 0
    assert result["share"] == {"A": 1.0}


def test_three_speakers_triple_overlap_counts_once():
    result = talk_share(
        {"A": [(0, 100)], "B": [(50, 150)], "C": [(80, 120)]}
    )
    assert result["per_speaker"] == {"A": 100, "B": 100, "C": 40}
    assert result["total"] == 150
    # [50, 80) A&B, [80, 100) A&B&C, [100, 120) B&C -> [50, 120)
    assert result["overlap"] == 70
    total_sum = 100 + 100 + 40
    assert result["share"] == {
        "A": pytest.approx(100 / total_sum),
        "B": pytest.approx(100 / total_sum),
        "C": pytest.approx(40 / total_sum),
    }


def test_unsorted_ranges_and_speakers():
    result = talk_share({"B": [(200, 300), (100, 150)], "A": [(5, 10)]})
    assert result["per_speaker"] == {"B": 150, "A": 5}
    assert result["total"] == 155
    assert result["overlap"] == 0


def test_touching_ranges_give_no_overlap():
    result = talk_share({"A": [(0, 50)], "B": [(50, 100)]})
    assert result["total"] == 100
    assert result["overlap"] == 0


def test_empty_range_list_yields_zero_share():
    result = talk_share({"A": [], "B": []})
    assert result == {
        "per_speaker": {"A": 0, "B": 0},
        "total": 0,
        "overlap": 0,
        "share": {"A": 0.0, "B": 0.0},
    }


def test_end_not_greater_than_start_raises_value_error():
    with pytest.raises(ValueError, match="start"):
        talk_share({"A": [(50, 50)]})
    with pytest.raises(ValueError, match="start"):
        talk_share({"A": [(50, 40)]})


def test_input_is_not_mutated():
    speakers = {"A": [(0, 100), (50, 150)], "B": [(120, 200)]}
    speaker_copy = {"A": [(0, 100), (50, 150)], "B": [(120, 200)]}
    ranges_copy = [(0, 100), (50, 150)]
    talk_share(speakers)
    assert speakers == speaker_copy
    assert speakers["A"] == ranges_copy
