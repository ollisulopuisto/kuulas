"""The Auto-Silence live preview's listening overlay: playback with the
previewed closed ranges as temporary gates, never committed.

Fake stream and fake clock as in test_engine.py; no audio device. Every
expected block is ``mixer.mix`` of the project with the ranges set as gates
(``ops.set_gate``): exactly what Accept would make, so the overlay sounds
like the result, edge ramps and all."""

import numpy as np
import pytest
from test_engine import (
    RATE,
    Clock,
    FakeSession,
    MemoryStore,
    install_rig,
    noise,
    project_with,
)

from kuulas import mixer, ops
from kuulas.engine import Engine

BLOCK = 1024


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


def make(clock, seconds=2.0):
    arrays = {"a": noise(seconds, seed=1), "b": noise(seconds, seed=2)}
    store = MemoryStore(arrays)
    session = FakeSession(project_with(arrays), store)
    return Engine(session, background=False, clock=clock), session, store


def gated(project, ranges):
    for track_id, r in ranges.items():
        project = ops.set_gate(project, track_id, r)
    return project


def blocks(engine, count):
    return np.concatenate([engine._render(BLOCK) for _ in range(count)])


def test_the_overlay_silences_what_accept_would_and_commits_nothing(rig, clock):
    engine, session, store = make(clock)
    before = session.state
    ranges = {"t-a": [(4096, 40000)], "t-b": [(10000, 20000)]}
    engine.set_silence_overlay(ranges)
    engine.play(0)
    out = blocks(engine, 48)
    want = mixer.mix(gated(before, ranges), store, 0, 48 * BLOCK).T
    np.testing.assert_array_equal(out, want)
    # Inside both closed ranges (past the ramps) nothing plays at all.
    assert not out[12000:19000].any()
    assert session.state is before
    assert engine.status()["silence_overlay"] is True


def test_without_an_overlay_playback_is_the_plain_mix(rig, clock):
    engine, session, store = make(clock)
    engine.play(0)
    np.testing.assert_array_equal(blocks(engine, 4),
                                  mixer.mix(session.state, store, 0, 4 * BLOCK).T)
    assert engine.status()["silence_overlay"] is False


def test_the_overlay_replaces_a_tracks_gate_as_accept_does(rig, clock):
    engine, session, store = make(clock)
    session.change(ops.set_gate(session.state, "t-a", [(0, 30000)]))
    ranges = {"t-a": [(20000, 25000)]}
    engine.set_silence_overlay(ranges)
    engine.play(0)
    np.testing.assert_array_equal(
        blocks(engine, 32),
        mixer.mix(gated(session.state, ranges), store, 0, 32 * BLOCK).T)


def test_edits_meanwhile_are_heard_with_the_overlay_on_top(rig, clock):
    engine, session, store = make(clock)
    ranges = {"t-a": [(0, 60000)]}
    engine.set_silence_overlay(ranges)
    engine.play(0)
    engine._render(BLOCK)
    louder = ops.set_track(session.state, "t-b", gain_db=6.0)
    session.change(louder)
    np.testing.assert_array_equal(
        engine._render(BLOCK), mixer.mix(gated(louder, ranges), store, BLOCK, BLOCK).T)
    assert session.state.track("t-a").gate == ()


def test_new_ranges_swap_in_at_the_next_block_without_a_restart(rig, clock):
    engine, session, store = make(clock)
    engine.set_silence_overlay({"t-a": [(0, 10000)]})
    engine.play(0)
    engine._render(BLOCK)
    seq = engine.status()["seq"]
    swapped = {"t-a": [(30000, 60000)], "t-b": [(0, 5000)]}
    engine.set_silence_overlay(swapped)
    np.testing.assert_array_equal(
        engine._render(BLOCK),
        mixer.mix(gated(session.state, swapped), store, BLOCK, BLOCK).T)
    status = engine.status()
    assert (status["seq"], status["playing"]) == (seq, True)


def test_clearing_the_overlay_restores_normal_playback_at_once(rig, clock):
    engine, session, store = make(clock)
    engine.set_silence_overlay({"t-a": [(0, 90000)], "t-b": [(0, 90000)]})
    engine.play(0)
    assert not engine._render(BLOCK)[BLOCK // 2:].any()
    engine.set_silence_overlay(None)
    np.testing.assert_array_equal(
        engine._render(BLOCK), mixer.mix(session.state, store, BLOCK, BLOCK).T)
    assert engine.status()["silence_overlay"] is False


def test_an_unknown_track_in_the_overlay_is_ignored(rig, clock):
    engine, session, store = make(clock)
    engine.set_silence_overlay({"gone": [(0, 1000)]})
    engine.play(0)
    np.testing.assert_array_equal(engine._render(BLOCK),
                                  mixer.mix(session.state, store, 0, BLOCK).T)


def test_a_clipboard_preview_plays_unchanged_and_the_overlay_comes_back(rig, clock):
    engine, session, store = make(clock)
    ranges = {"t-a": [(0, 60000)]}
    engine.set_silence_overlay(ranges)
    temp = ops.set_track(session.state, "t-b", gain_db=-6.0)
    engine.play_preview(temp)
    np.testing.assert_array_equal(engine._render(BLOCK),
                                  mixer.mix(temp, store, 0, BLOCK).T)
    engine.stop()
    engine.play(0)
    np.testing.assert_array_equal(
        engine._render(BLOCK), mixer.mix(gated(session.state, ranges), store, 0, BLOCK).T)


def test_the_overlay_set_during_a_clipboard_preview_waits_for_its_end(rig, clock):
    engine, session, store = make(clock)
    temp = ops.set_track(session.state, "t-b", gain_db=-6.0)
    engine.play_preview(temp)
    ranges = {"t-a": [(0, 60000)]}
    engine.set_silence_overlay(ranges)
    np.testing.assert_array_equal(engine._render(BLOCK),
                                  mixer.mix(temp, store, 0, BLOCK).T)
    engine.play(0)
    np.testing.assert_array_equal(
        engine._render(BLOCK), mixer.mix(gated(session.state, ranges), store, 0, BLOCK).T)


def test_the_rate_is_the_projects(rig, clock):
    engine, _, _ = make(clock)
    assert engine.rate == RATE
