from __future__ import annotations

import copy

from kuulas.take_list import take_rows, unused_count


def test_take_rows_ordering_newest_first():
    takes = [
        {"name": "Take 1", "file": "take1.wav", "created": 100.0, "duration_s": 5.0},
        {"name": "Take 3", "file": "take3.wav", "created": 300.0, "duration_s": 15.0},
        {"name": "Take 2", "file": "take2.wav", "created": 200.0, "duration_s": 10.0},
    ]
    rows = take_rows(takes, {"take1.wav", "take3.wav"})
    assert [r["name"] for r in rows] == ["Take 3", "Take 2", "Take 1"]
    assert [r["created"] for r in rows] == [300.0, 200.0, 100.0]


def test_take_rows_tie_breaking_by_name_case_insensitive():
    takes = [
        {"name": "bravo", "file": "b.wav", "created": 100.0, "duration_s": 1.0},
        {"name": "Alpha", "file": "a.wav", "created": 100.0, "duration_s": 1.0},
        {"name": "charlie", "file": "c.wav", "created": 100.0, "duration_s": 1.0},
    ]
    rows = take_rows(takes, set())
    assert [r["name"] for r in rows] == ["Alpha", "bravo", "charlie"]


def test_take_rows_used_flag():
    takes = [
        {"name": "Take 1", "file": "take1.wav", "created": 100.0, "duration_s": 5.0},
        {"name": "Take 2", "file": "take2.wav", "created": 200.0, "duration_s": 10.0},
    ]
    used = {"take1.wav"}
    rows = take_rows(takes, used)
    row_by_name = {r["name"]: r for r in rows}
    assert row_by_name["Take 1"]["used"] is True
    assert row_by_name["Take 2"]["used"] is False


def test_take_rows_missing_keys_default_gracefully():
    takes = [
        {"file": "recordings/interview_01.flac"},  # missing name, created, duration_s
        {"name": "Take B", "file": "take_b.wav", "duration_s": None, "created": None},
    ]
    rows = take_rows(takes, set())
    assert len(rows) == 2

    row0 = next(r for r in rows if r["file"] == "recordings/interview_01.flac")
    assert row0["name"] == "interview_01"  # stem of file
    assert row0["created"] == 0.0
    assert row0["duration_s"] == 0.0
    assert row0["used"] is False

    row1 = next(r for r in rows if r["name"] == "Take B")
    assert row1["created"] == 0.0
    assert row1["duration_s"] == 0.0


def test_take_rows_never_drops_takes_with_zero_duration_or_unused():
    takes = [
        {"name": "Zero Duration", "file": "zero.wav", "created": 10.0, "duration_s": 0.0},
        {
            "name": "Unused Take",
            "file": "unused.wav",
            "created": 20.0,
            "duration_s": 12.0,
        },
    ]
    rows = take_rows(takes, set())
    assert len(rows) == 2
    assert {r["name"] for r in rows} == {"Zero Duration", "Unused Take"}


def test_take_rows_empty_input():
    assert take_rows([], {"some.wav"}) == []
    assert take_rows(None, {"some.wav"}) == []
    assert take_rows([], set()) == []


def test_unused_count():
    rows = [
        {"name": "A", "file": "a.wav", "used": True},
        {"name": "B", "file": "b.wav", "used": False},
        {"name": "C", "file": "c.wav", "used": False},
    ]
    assert unused_count(rows) == 2
    assert unused_count([]) == 0
    assert unused_count([{"used": True}]) == 0


def test_take_rows_does_not_mutate_input():
    takes = [
        {"name": "Original", "file": "orig.wav", "created": 50.0, "duration_s": 3.0}
    ]
    takes_snapshot = copy.deepcopy(takes)
    used = {"orig.wav"}
    used_snapshot = set(used)

    rows = take_rows(takes, used)
    assert len(rows) == 1
    assert takes == takes_snapshot
    assert used == used_snapshot
