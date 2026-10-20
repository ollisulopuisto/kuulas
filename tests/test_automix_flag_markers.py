"""Tests for turning parsed flags into marker plans (T68)."""

from kuulas.automix_flag_markers import flag_markers


def test_empty_input():
    assert flag_markers([], 48000) == []


def test_threshold_filter():
    flags = [
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "A",
            "kind": "block",
            "off_db": 2.5,
            "gain_db": -2.5,
        },
        {
            "start_s": 20.0,
            "end_s": 22.0,
            "name": "B",
            "kind": "block",
            "off_db": -3.0,
            "gain_db": 3.0,
        },
        {
            "start_s": 30.0,
            "end_s": 32.0,
            "name": "C",
            "kind": "block",
            "off_db": 4.1,
            "gain_db": -4.1,
        },
    ]
    # Default min_abs_db=3.0: 2.5 is dropped, -3.0 and 4.1 are kept.
    markers = flag_markers(flags, 1000)
    assert len(markers) == 2
    assert markers[0]["names"] == ["B"]
    assert markers[0]["worst_db"] == -3.0
    assert markers[1]["names"] == ["C"]
    assert markers[1]["worst_db"] == 4.1


def test_min_abs_db_zero():
    flags = [
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "A",
            "kind": "block",
            "off_db": 0.5,
            "gain_db": -0.5,
        },
        {
            "start_s": 20.0,
            "end_s": 22.0,
            "name": "B",
            "kind": "block",
            "off_db": -0.1,
            "gain_db": 0.1,
        },
    ]
    markers = flag_markers(flags, 1000, min_abs_db=0.0)
    assert len(markers) == 2


def test_include_loud_option():
    flags = [
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "A",
            "kind": "loud",
            "off_db": 6.0,
            "gain_db": None,
        },
        {
            "start_s": 20.0,
            "end_s": 22.0,
            "name": "B",
            "kind": "block",
            "off_db": -5.0,
            "gain_db": 5.0,
        },
    ]
    markers_without = flag_markers(flags, 1000, include_loud=False)
    assert len(markers_without) == 1
    assert markers_without[0]["names"] == ["B"]

    markers_with = flag_markers(flags, 1000, include_loud=True)
    assert len(markers_with) == 2
    assert markers_with[0]["names"] == ["A"]
    assert markers_with[1]["names"] == ["B"]


def test_unsorted_input():
    flags = [
        {
            "start_s": 30.0,
            "end_s": 32.0,
            "name": "Later",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "Earlier",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
    ]
    markers = flag_markers(flags, 1000)
    assert len(markers) == 2
    assert markers[0]["names"] == ["Earlier"]
    assert markers[1]["names"] == ["Later"]


def test_merging_within_gap():
    flags = [
        {
            "start_s": 10.0,
            "end_s": 14.0,
            "name": "Tuukka",
            "kind": "block",
            "off_db": 4.0,
            "gain_db": -4.0,
        },
        {
            "start_s": 11.5,
            "end_s": 16.0,
            "name": "Aame",
            "kind": "loud",
            "off_db": 7.5,
            "gain_db": None,
        },
        {
            "start_s": 11.8,
            "end_s": 13.0,
            "name": "Tuukka",
            "kind": "block",
            "off_db": -6.0,
            "gain_db": 6.0,
        },
    ]
    # merge_gap_s=2.0 default; 11.5 and 11.8 are within 2.0s of 10.0
    markers = flag_markers(flags, 48000)
    assert len(markers) == 1
    m = markers[0]
    assert m["frame"] == 480000
    assert m["end_frame"] == 768000  # 16.0 * 48000
    assert m["names"] == ["Tuukka", "Aame"]  # unique, in order
    assert m["kinds"] == ["block", "loud"]  # sorted unique list
    assert m["worst_db"] == 7.5  # abs(7.5) > abs(-6.0) > abs(4.0)
    assert m["count"] == 3


def test_no_merge_beyond_gap():
    flags = [
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "Tuukka",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
        {
            "start_s": 12.5,
            "end_s": 14.0,
            "name": "Tuukka",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
    ]
    # Gap is 2.5s > default 2.0s
    markers = flag_markers(flags, 1000)
    assert len(markers) == 2
    assert markers[0]["frame"] == 10000
    assert markers[1]["frame"] == 12500


def test_gap_measured_from_marker_start():
    # Flag 1 at 10.0
    # Flag 2 at 11.5 (diff from 10.0 is 1.5 <= 2.0 -> merges)
    # Flag 3 at 12.5 (diff from 10.0 is 2.5 > 2.0 -> separate marker)
    flags = [
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "A",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
        {
            "start_s": 11.5,
            "end_s": 13.0,
            "name": "B",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
        {
            "start_s": 12.5,
            "end_s": 14.0,
            "name": "C",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        },
    ]
    markers = flag_markers(flags, 1000, merge_gap_s=2.0)
    assert len(markers) == 2
    assert markers[0]["names"] == ["A", "B"]
    assert markers[0]["count"] == 2
    assert markers[1]["names"] == ["C"]
    assert markers[1]["count"] == 1


def test_worst_db_signed_negative():
    flags = [
        {
            "start_s": 10.0,
            "end_s": 12.0,
            "name": "A",
            "kind": "block",
            "off_db": 4.0,
            "gain_db": -4.0,
        },
        {
            "start_s": 10.5,
            "end_s": 12.0,
            "name": "B",
            "kind": "block",
            "off_db": -8.5,
            "gain_db": 8.5,
        },
    ]
    markers = flag_markers(flags, 1000)
    assert len(markers) == 1
    assert markers[0]["worst_db"] == -8.5


def test_rate_conversion_rounding():
    flags = [
        {
            "start_s": 1.00001,
            "end_s": 2.00009,
            "name": "A",
            "kind": "block",
            "off_db": 5.0,
            "gain_db": -5.0,
        }
    ]
    markers = flag_markers(flags, 44100)
    assert len(markers) == 1
    assert markers[0]["frame"] == round(1.00001 * 44100)
    assert markers[0]["end_frame"] == round(2.00009 * 44100)
