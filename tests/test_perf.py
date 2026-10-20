"""Cheap named counters for the performance report. They only count: the audio path
renders exactly what it did before."""

import numpy as np
import pytest
from test_engine import Clock, install_rig, make, noise, project_with

from kuulas import mixer, perf


def test_note_keeps_count_total_and_max():
    c = perf.Counters()
    for v in (1.0, 5.0, 3.0):
        c.note("x", v)
    assert c.snapshot()["x"] == {"count": 3, "total": 9.0, "max": 5.0}


def test_delta_subtracts_the_start_and_keeps_names_that_moved():
    c = perf.Counters()
    c.note("old", 1.0)
    before = c.snapshot()
    c.note("old", 2.0)
    c.note("new", 4.0)
    delta = perf.delta(before, c.snapshot())
    assert delta["old"]["count"] == 1
    assert delta["old"]["total"] == 2.0
    assert delta["new"]["count"] == 1


def test_delta_drops_names_that_did_not_move():
    c = perf.Counters()
    c.note("still", 1.0)
    before = c.snapshot()
    assert perf.delta(before, c.snapshot()) == {}


def test_reset_max_forgets_old_peaks():
    c = perf.Counters()
    c.note("x", 99.0)
    c.reset_max()
    c.note("x", 1.0)
    assert c.snapshot()["x"]["max"] == 1.0


def test_mixer_counts_clips_scanned_and_mixed_per_track():
    arrays = {"m0": noise(2, channels=1, seed=1), "m1": noise(2, channels=1, seed=2)}
    project = project_with(arrays)
    store = make_store(arrays)
    before = perf.COUNTERS.snapshot()
    out = mixer.mix(project, store, 0, 1024)
    moved = perf.delta(before, perf.COUNTERS.snapshot())
    assert out.shape == (2, 1024)
    assert moved["mixer.clips_scanned"]["count"] == 2  # two tracks
    assert moved["mixer.clips_scanned"]["total"] == 2  # one clip on each
    assert moved["mixer.clips_mixed"]["total"] == 2


def make_store(arrays):
    from test_engine import MemoryStore  # noqa: PLC0415 - beside its only user

    return MemoryStore(arrays)


def test_mixing_is_deterministic_with_counting_on():
    arrays = {"m0": noise(2, channels=1, seed=1)}
    project = project_with(arrays)
    store = make_store(arrays)
    assert np.array_equal(mixer.mix(project, store, 0, 2048),
                          mixer.mix(project, store, 0, 2048))


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


def test_engine_notes_the_render_time_of_every_block(rig):
    engine, _session, _store = make(rig, Clock())
    engine.play(0)
    before = perf.COUNTERS.snapshot()
    for _ in range(5):
        rig.stream.pump()
    moved = perf.delta(before, perf.COUNTERS.snapshot())
    assert moved["engine.callback_ms"]["count"] == 5
    assert moved["engine.mix_ms"]["count"] >= 5
    assert moved["engine.callback_ms"]["max"] >= 0.0
    engine.close()
