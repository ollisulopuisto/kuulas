from __future__ import annotations

import numpy as np
import pytest

from kuulas import clock, messages
from kuulas.edit_points import (
    MODES,
    EditPointsError,
    edit_points,
    next_mode,
    next_point,
    previous_point,
)
from kuulas.model import Clip, Media, Project, Track


def _make_project() -> Project:
    rate = 48000
    m1 = Media(id="m1", name="m1.wav", channels=1, frames=rate * 10)
    m2 = Media(id="m2", name="m2.wav", channels=1, frames=rate * 10)
    t1 = Track(id="t1", name="Track 1", clips=(
        Clip(id="c1", media="m1", start=1000, offset=0, length=2000),
        Clip(id="c2", media="m1", start=3000, offset=2000, length=2000),
    ))
    t2 = Track(id="t2", name="Track 2", clips=(
        Clip(id="c3", media="m2", start=5000, offset=0, length=1000),
    ))
    return Project(rate=rate, media=(m1, m2), tracks=(t1, t2))


def test_adjacent_clips_give_one_edge():
    rate = 48000
    # Two adjacent clips on the same track: c1 ends at 2000, c2 starts at 2000
    t = Track(id="t1", name="Track 1", clips=(
        Clip(id="c1", media="m1", start=1000, offset=0, length=1000),
        Clip(id="c2", media="m1", start=2000, offset=1000, length=1000),
    ))
    p = Project(rate=rate, tracks=(t,))
    points = edit_points(p, {}, {}, mode="edges")
    # Edges are [1000, 2000, 3000] - 2000 is shared and de-duplicated
    assert points == [1000, 2000, 3000]


def test_edges_mode_muted_clip_and_muted_track():
    rate = 48000
    t1 = Track(id="t1", name="Track 1", mute=False, clips=(
        Clip(id="c1", media="m1", start=1000, offset=0, length=1000, muted=False),
        Clip(id="c2", media="m1", start=2500, offset=0, length=1000, muted=True),
    ))
    t2 = Track(id="t2", name="Track 2", mute=True, clips=(
        Clip(id="c3", media="m2", start=5000, offset=0, length=1000, muted=False),
    ))
    p = Project(rate=rate, tracks=(t1, t2))
    points = edit_points(p, {}, {}, mode="edges")
    # Only c1 is unmuted on an unmuted track
    assert points == [1000, 2000]


def test_transients_mode():
    p = _make_project()
    rate = p.rate
    # Transients in flicks from media start
    # m1 has onsets at media frames 500 and 1500 (within c1: start 1000, offset 0)
    # Timeline frames should be 1000 + 500 = 1500, and 1000 + 1500 = 2500
    flick_500 = clock.frames_to_flicks(500, rate)
    flick_1500 = clock.frames_to_flicks(1500, rate)
    onsets = {"m1": np.array([flick_500, flick_1500], dtype=np.int64)}

    points = edit_points(p, {}, onsets, mode="transients")
    assert points == [1500, 2500]


def test_transients_muted_clip_and_muted_track():
    rate = 48000
    flick = clock.frames_to_flicks(500, rate)
    onsets = {"m1": [flick]}
    # Muted clip
    t1 = Track(id="t1", name="Track 1", clips=(
        Clip(id="c1", media="m1", start=1000, offset=0, length=1000, muted=True),
    ))
    p1 = Project(rate=rate, tracks=(t1,))
    assert edit_points(p1, {}, onsets, mode="transients") == []

    # Muted track
    t2 = Track(id="t2", name="Track 2", mute=True, clips=(
        Clip(id="c2", media="m1", start=1000, offset=0, length=1000, muted=False),
    ))
    p2 = Project(rate=rate, tracks=(t2,))
    assert edit_points(p2, {}, onsets, mode="transients") == []


def test_words_mode():
    p = _make_project()
    rate = p.rate
    # Word starts in flicks from media start
    # c1 has start=1000, offset=0. Word at frame 400 -> timeline 1400
    # c2 has start=3000, offset=2000. Word at frame 2500 -> timeline 3500
    w1_s = clock.frames_to_flicks(400, rate)
    w1_e = clock.frames_to_flicks(600, rate)
    w2_s = clock.frames_to_flicks(2500, rate)
    w2_e = clock.frames_to_flicks(2700, rate)

    transcripts = {
        "m1": [
            {"w": "hello", "s": w1_s, "e": w1_e},
            {"w": "world", "s": w2_s, "e": w2_e},
        ]
    }
    points = edit_points(p, transcripts, {}, mode="words")
    assert points == [1400, 3500]


def test_words_muted_clip_and_muted_track():
    rate = 48000
    w_s = clock.frames_to_flicks(400, rate)
    w_e = clock.frames_to_flicks(600, rate)
    transcripts = {"m1": [{"w": "hi", "s": w_s, "e": w_e}]}

    # Muted clip
    t1 = Track(id="t1", name="T1", clips=(
        Clip(id="c1", media="m1", start=1000, offset=0, length=1000, muted=True),
    ))
    p1 = Project(rate=rate, tracks=(t1,))
    assert edit_points(p1, transcripts, {}, mode="words") == []

    # Muted track
    t2 = Track(id="t2", name="T2", mute=True, clips=(
        Clip(id="c2", media="m1", start=1000, offset=0, length=1000, muted=False),
    ))
    p2 = Project(rate=rate, tracks=(t2,))
    assert edit_points(p2, transcripts, {}, mode="words") == []


def test_track_filter():
    p = _make_project()
    # Edges on all tracks
    all_edges = edit_points(p, {}, {}, mode="edges")
    # c1: 1000..3000, c2: 3000..5000, c3: 5000..6000
    assert all_edges == [1000, 3000, 5000, 6000]

    # Track filter t1 only: c1 (1000..3000) and c2 (3000..5000)
    t1_edges = edit_points(p, {}, {}, mode="edges", track_id="t1")
    assert t1_edges == [1000, 3000, 5000]

    # Track filter t2 only: c3 (5000..6000)
    t2_edges = edit_points(p, {}, {}, mode="edges", track_id="t2")
    assert t2_edges == [5000, 6000]

    # Transients with track filter
    rate = p.rate
    flick_m1 = clock.frames_to_flicks(500, rate)
    flick_m2 = clock.frames_to_flicks(200, rate)
    onsets = {
        "m1": [flick_m1],  # c1 timeline: 1000 + 500 = 1500 (t1)
        "m2": [flick_m2],  # c3 timeline: 5000 + 200 = 5200 (t2)
    }
    assert edit_points(p, {}, onsets, mode="transients", track_id="t1") == [1500]
    assert edit_points(p, {}, onsets, mode="transients", track_id="t2") == [5200]
    assert edit_points(p, {}, onsets, mode="transients", track_id=None) == [1500, 5200]

    # Words with track filter
    w1_s = clock.frames_to_flicks(400, rate)
    w1_e = clock.frames_to_flicks(600, rate)
    w2_s = clock.frames_to_flicks(100, rate)
    w2_e = clock.frames_to_flicks(300, rate)
    transcripts = {
        "m1": [{"w": "first", "s": w1_s, "e": w1_e}],  # timeline 1400 (t1)
        "m2": [{"w": "second", "s": w2_s, "e": w2_e}],  # timeline 5100 (t2)
    }
    assert edit_points(p, transcripts, {}, mode="words", track_id="t1") == [1400]
    assert edit_points(p, transcripts, {}, mode="words", track_id="t2") == [5100]
    assert edit_points(p, transcripts, {}, mode="words", track_id=None) == [1400, 5100]


def test_next_and_previous_point():
    points = [100, 200, 300, 400]

    # next_point: strictly after, None at ends
    assert next_point(points, 50) == 100
    assert next_point(points, 100) == 200
    assert next_point(points, 150) == 200
    assert next_point(points, 300) == 400
    assert next_point(points, 400) is None
    assert next_point(points, 500) is None
    assert next_point([], 100) is None

    # previous_point: strictly before, None at ends
    assert previous_point(points, 500) == 400
    assert previous_point(points, 400) == 300
    assert previous_point(points, 250) == 200
    assert previous_point(points, 200) == 100
    assert previous_point(points, 100) is None
    assert previous_point(points, 50) is None
    assert previous_point([], 100) is None


def test_mode_cycle():
    assert MODES == ("edges", "transients", "words")
    assert next_mode("edges") == "transients"
    assert next_mode("transients") == "words"
    assert next_mode("words") == "edges"

    with pytest.raises(EditPointsError) as exc_info:
        next_mode("other")
    assert exc_info.value.key == "error.edit_points.unknown_mode"
    assert "Unknown edit point mode: other." in str(exc_info.value)

    # Check Finnish translation
    messages.set_language("fi")
    try:
        assert "Tuntematon leikkauspistetila: other." in str(exc_info.value)
    finally:
        messages.set_language("en")


def test_invalid_mode_raises():
    p = _make_project()
    with pytest.raises(EditPointsError) as exc_info:
        edit_points(p, {}, {}, mode="nonexistent")
    assert exc_info.value.key == "error.edit_points.unknown_mode"
