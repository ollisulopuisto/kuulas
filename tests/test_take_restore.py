from __future__ import annotations

import pytest

from kuulas.take_restore import restore_plan


def test_restore_plan_new_track_original():
    # With original
    plan = restore_plan(
        "new_track_original",
        original={"start": 1200, "track_id": "t1"},
        playhead=5000,
        duration=48000,
        current_track_id="t2",
    )
    assert plan == {
        "target": "new_track",
        "track_id": None,
        "start": 1200,
        "replaces": False,
    }

    # Without original: falls back to playhead
    plan_no_orig = restore_plan(
        "new_track_original",
        original=None,
        playhead=5000,
        duration=48000,
        current_track_id="t2",
    )
    assert plan_no_orig == {
        "target": "new_track",
        "track_id": None,
        "start": 5000,
        "replaces": False,
    }


def test_restore_plan_playhead():
    # With current track id
    plan = restore_plan(
        "playhead",
        original={"start": 1200, "track_id": "t1"},
        playhead=3500,
        duration=48000,
        current_track_id="t2",
    )
    assert plan == {
        "target": "track",
        "track_id": "t2",
        "start": 3500,
        "replaces": True,
    }

    # With missing current track id: falls back to new_track
    plan_no_track = restore_plan(
        "playhead",
        original=None,
        playhead=3500,
        duration=48000,
        current_track_id=None,
    )
    assert plan_no_track == {
        "target": "new_track",
        "track_id": None,
        "start": 3500,
        "replaces": True,
    }


def test_restore_plan_original():
    # With original track_id and start
    plan = restore_plan(
        "original",
        original={"start": 2400, "track_id": "t_orig"},
        playhead=8000,
        duration=48000,
        current_track_id="t_curr",
    )
    assert plan == {
        "target": "track",
        "track_id": "t_orig",
        "start": 2400,
        "replaces": True,
    }

    # With original track_id None: target new_track
    plan_none_track = restore_plan(
        "original",
        original={"start": 2400, "track_id": None},
        playhead=8000,
        duration=48000,
        current_track_id="t_curr",
    )
    assert plan_none_track == {
        "target": "new_track",
        "track_id": None,
        "start": 2400,
        "replaces": True,
    }

    # With original None: target new_track, start playhead
    plan_none = restore_plan(
        "original",
        original=None,
        playhead=8000,
        duration=48000,
        current_track_id="t_curr",
    )
    assert plan_none == {
        "target": "new_track",
        "track_id": None,
        "start": 8000,
        "replaces": True,
    }

    # With original missing start: falls back to playhead
    plan_missing_start = restore_plan(
        "original",
        original={"track_id": "t_orig"},
        playhead=8000,
        duration=48000,
        current_track_id="t_curr",
    )
    assert plan_missing_start == {
        "target": "track",
        "track_id": "t_orig",
        "start": 8000,
        "replaces": True,
    }


def test_restore_plan_clipboard():
    plan = restore_plan(
        "clipboard",
        original={"start": 1000, "track_id": "t1"},
        playhead=5000,
        duration=48000,
        current_track_id="t2",
    )
    assert plan == {
        "target": "clipboard",
        "track_id": None,
        "start": None,
        "replaces": False,
    }

    plan_no_orig = restore_plan(
        "clipboard",
        original=None,
        playhead=5000,
        duration=48000,
        current_track_id=None,
    )
    assert plan_no_orig == {
        "target": "clipboard",
        "track_id": None,
        "start": None,
        "replaces": False,
    }


def test_restore_plan_clamps_negative_start():
    plan = restore_plan(
        "new_track_original",
        original={"start": -250, "track_id": "t1"},
        playhead=-100,
        duration=48000,
        current_track_id="t2",
    )
    assert plan["start"] == 0

    plan_playhead = restore_plan(
        "playhead",
        original=None,
        playhead=-500,
        duration=48000,
        current_track_id="t1",
    )
    assert plan_playhead["start"] == 0


def test_restore_plan_unknown_mode_raises():
    with pytest.raises(ValueError, match="Unknown mode"):
        restore_plan(
            "nonexistent_mode",
            original=None,
            playhead=0,
            duration=48000,
            current_track_id=None,
        )


def test_restore_plan_default_mode():
    plan = restore_plan(
        original={"start": 600, "track_id": "t1"},
        playhead=1200,
        duration=48000,
        current_track_id="t2",
    )
    assert plan["target"] == "new_track"
    assert plan["start"] == 600
    assert plan["replaces"] is False
