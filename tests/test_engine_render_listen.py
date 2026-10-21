"""Listening to the rendered mix: the engine plays a stand-in project (one clip of the
rendered file at its place on the timeline) instead of the edit, through its normal
machinery, and the edit itself is never touched.

Fake stream and fake clock as in test_engine.py; no audio device."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import soxr
from test_engine import Clock, FakeSession, MemoryStore, install_rig, project_with

from kuulas import mixer, render_listen
from kuulas.engine import Engine

RATE = 48000
BLOCK = 1024


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


def tone(hz: float, seconds: float, rate: int = RATE, amp: float = 0.3) -> np.ndarray:
    t = np.arange(round(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def render_file(path: Path, seconds: float = 1.0, rate: int = RATE,
                subtype: str = "PCM_24") -> np.ndarray:
    left, right = tone(440, seconds, rate), tone(660, seconds, rate, 0.2)
    data = np.stack([left, right], axis=1)
    sf.write(path, data, rate, subtype=subtype)
    return sf.read(path, dtype="float32", always_2d=True)[0].T  # as stored (24-bit)


def setup(rig, clock, tmp_path, *, offset=0, rate=RATE, seconds=1.0):
    del rig
    main_audio = {"m": (np.ones((1, 4 * RATE)) * 0.05).astype(np.float32)}
    store = MemoryStore(main_audio)
    main = project_with(main_audio)
    session = FakeSession(main, store)
    engine = Engine(session, background=False, clock=clock)
    path = tmp_path / "mix.wav"
    stored = render_file(path, seconds, rate)
    source = render_listen.FileSource(path, RATE)
    project = render_listen.listen_project(RATE, source, offset)
    return engine, session, store, main, source, project, stored


def listen(engine, source, project, keep=None):
    engine.set_listen_source(project, {source.media_id: source}, keep=keep)


def test_the_render_is_heard_at_its_place_on_the_timeline(rig, clock, tmp_path):
    offset = 3 * BLOCK + 100
    engine, session, _, main, source, project, stored = setup(rig, clock, tmp_path,
                                                              offset=offset)
    listen(engine, source, project)
    assert engine.listening is True
    engine.play(0)
    out = np.concatenate([engine._render(BLOCK) for _ in range(6)])
    assert not np.any(out[:offset])  # outside the render's span: silence
    np.testing.assert_allclose(out[offset:6 * BLOCK], stored[:, :6 * BLOCK - offset].T,
                               atol=1e-6)
    assert session.state is main  # the project itself is never touched


def test_seek_moves_within_the_render(rig, clock, tmp_path):
    engine, _, _, _, source, project, stored = setup(rig, clock, tmp_path, offset=1000)
    listen(engine, source, project)
    engine.play(0)
    engine._render(BLOCK)
    engine.seek(1000 + 5000)
    out = engine._render(BLOCK)
    np.testing.assert_allclose(out, stored[:, 5000:5000 + BLOCK].T, atol=1e-6)


def test_a_loop_wraps_inside_the_render(rig, clock, tmp_path):
    engine, _, _, _, source, project, _ = setup(rig, clock, tmp_path, offset=0)
    listen(engine, source, project)
    engine.play(0, loop=(1000, 1000 + 3 * BLOCK))
    for _ in range(12):
        engine._render(BLOCK)
    status = engine.status()
    assert status["loop"] == [1000, 1000 + 3 * BLOCK]
    assert status["playing"] is True
    assert 1000 <= status["position"] < 1000 + 3 * BLOCK


def test_clearing_restores_the_edit_at_once(rig, clock, tmp_path):
    engine, _, store, main, source, project, _ = setup(rig, clock, tmp_path)
    listen(engine, source, project)
    engine.play(0)
    engine._render(BLOCK)
    seq = engine.status()["seq"]
    engine.clear_listen_source()
    assert engine.listening is False
    out = engine._render(BLOCK)
    np.testing.assert_allclose(out, mixer.mix(main, store, BLOCK, BLOCK).T, atol=1e-6)
    assert engine.status()["playing"] is True
    assert engine.status()["seq"] == seq  # nothing restarted


def test_an_edit_while_listening_is_kept_for_afterwards(rig, clock, tmp_path):
    engine, session, store, _main, source, project, stored = setup(rig, clock, tmp_path)
    listen(engine, source, project)
    edited = project_with({"m": store.arrays["m"]}, starts={"m": 10})
    session.change(edited)
    engine.play(0)
    out = engine._render(BLOCK)
    np.testing.assert_allclose(out, stored[:, :BLOCK].T, atol=1e-6)  # still the render
    engine.clear_listen_source()
    engine.seek(0)
    out = engine._render(BLOCK)
    np.testing.assert_allclose(out, mixer.mix(edited, store, 0, BLOCK).T, atol=1e-6)


def test_a_change_that_makes_the_render_stale_ends_listening_by_itself(rig, clock,
                                                                       tmp_path):
    engine, session, store, main, source, project, _ = setup(rig, clock, tmp_path)
    listen(engine, source, project, keep=lambda p: p is main)
    session.change(main)
    assert engine.listening is True
    edited = project_with({"m": store.arrays["m"]}, starts={"m": 10})
    session.change(edited)
    assert engine.listening is False
    engine.play(0)
    out = engine._render(BLOCK)
    np.testing.assert_allclose(out, mixer.mix(edited, store, 0, BLOCK).T, atol=1e-6)


def test_a_failing_keep_check_ends_listening_and_never_raises(rig, clock, tmp_path):
    engine, session, _, main, source, project, _ = setup(rig, clock, tmp_path)

    def broken(_p):
        raise RuntimeError("boom")

    listen(engine, source, project, keep=broken)
    session.change(main)
    assert engine.listening is False


def test_a_file_at_another_rate_is_resampled_to_the_project_rate(rig, clock, tmp_path):
    engine, _, _, _, source, project, stored = setup(rig, clock, tmp_path, rate=44100)
    assert source.frames == round(stored.shape[1] * RATE / 44100)
    listen(engine, source, project)
    engine.play(0)
    out = np.concatenate([engine._render(BLOCK) for _ in range(20)])
    expected = soxr.resample(stored.T, 44100, RATE, quality="HQ")
    # The middle (not the filter's edges) matches a one-shot resample closely.
    a, b = 2000, 20 * BLOCK - 2000
    np.testing.assert_allclose(out[a:b], expected[a:b], atol=2e-3)


def test_a_short_or_damaged_read_plays_silence_not_an_error(rig, clock, tmp_path):
    engine, _, _, _, source, project, _ = setup(rig, clock, tmp_path)
    listen(engine, source, project)
    Path(source.path).write_bytes(b"RIFF garbage")  # the file changed under us
    source.close()
    engine.play(0)
    out = engine._render(BLOCK)
    assert out.shape == (BLOCK, 2)
    assert engine.status()["failed_blocks"] == 0


def test_past_a_range_render_the_timeline_goes_on_in_silence(rig, clock, tmp_path):
    """A range render is shorter than the edit: playing past its end (or switching
    to it with the playhead beyond it) is silence on the edit's own timeline, not the end
    of the programme."""
    del rig
    path = tmp_path / "mix.wav"
    render_file(path, seconds=0.05)
    source = render_listen.FileSource(path, RATE)
    real = project_with({"m": (np.ones((1, 4 * RATE)) * 0.05).astype(np.float32)})
    project = render_listen.listen_project(RATE, source, 1000, length=real.length)
    assert project.length == real.length
    session = FakeSession(real, MemoryStore({"m": np.zeros((1, 4 * RATE), np.float32)}))
    engine = Engine(session, background=False, clock=clock)
    listen(engine, source, project)
    engine.play(2 * RATE)
    out = engine._render(BLOCK)
    assert engine.status()["playing"] is True
    assert not np.any(out)


def test_status_says_whether_the_render_is_playing(rig, clock, tmp_path):
    engine, _, _, _, source, project, _ = setup(rig, clock, tmp_path)
    assert engine.status()["listen"] is False
    listen(engine, source, project)
    assert engine.status()["listen"] is True
