"""A clipboard preview started while the timeline plays is mixed into it (owner,
2026-10-21: "the clipboard should MIX INTO the playback, not TAKE OVER").

Fake stream and fake clock as in test_engine.py; no audio device."""

import threading
import time

import numpy as np
import pytest
from test_engine import RATE, Clock, FakeSession, MemoryStore, install_rig, project_with

from kuulas import mixer, preview_level
from kuulas.engine import Engine


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


BLOCK = 1024


def tone(hz: float, seconds: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)[None, :]


def setup(rig, clock, preview_seconds=0.2, store_cls=MemoryStore, amp=0.3):
    arrays = {"m": tone(440, 4.0), "p": tone(1000, preview_seconds, amp)}
    store = store_cls(arrays)
    main = project_with({"m": arrays["m"]})
    temp = project_with({"p": arrays["p"]})
    session = FakeSession(main, store)
    engine = Engine(session, background=False, clock=clock)
    return engine, session, store, main, temp


def test_preview_while_playing_mixes_in_and_leaves_the_timeline_alone(rig, clock):
    engine, _, store, main, temp = setup(rig, clock)
    engine.play(0)
    engine._render(BLOCK)
    before = engine.status()
    engine.play_preview(temp)
    after = engine.status()
    for key in ("position", "t", "seq", "playing", "end", "until", "speed"):
        assert after[key] == before[key], key
    assert after["preview"] is False
    assert after["mix_preview"]["playing"] is True
    out = engine._render(BLOCK)
    expected = (mixer.mix(main, store, BLOCK, BLOCK).T
                + mixer.mix(temp, store, 0, BLOCK).T)
    np.testing.assert_allclose(out, expected, atol=1e-6)
    assert engine.status()["seq"] == before["seq"]
    assert not any(s.closed or not s.active for s in rig.streams)


def test_the_timeline_keeps_its_place_and_the_voice_ends_by_itself(rig, clock):
    engine, _, store, main, temp = setup(rig, clock, preview_seconds=0.1)
    engine.play(0)
    engine._render(BLOCK)
    seq = engine.status()["seq"]
    engine.play_preview(temp)
    blocks = 0
    while engine.status()["mix_preview"] is not None:
        engine._render(BLOCK)
        blocks += 1
        assert blocks < 20
    status = engine.status()
    assert status["playing"] is True
    assert status["seq"] == seq
    first = (blocks + 1) * BLOCK
    out = engine._render(BLOCK)
    np.testing.assert_array_equal(out, mixer.mix(main, store, first, BLOCK).T)
    assert engine.status()["preview_seq"] > seq  # the page can tell it ended


def test_stop_preview_removes_only_the_voice(rig, clock):
    engine, _, store, main, temp = setup(rig, clock, preview_seconds=1.0)
    engine.play(0)
    engine._render(BLOCK)
    engine.play_preview(temp)
    engine._render(BLOCK)
    seq = engine.status()["seq"]
    engine.stop_preview()
    status = engine.status()
    assert status["mix_preview"] is None
    assert status["playing"] is True
    assert status["seq"] == seq
    out = engine._render(BLOCK)
    np.testing.assert_array_equal(out, mixer.mix(main, store, 2 * BLOCK, BLOCK).T)


def test_a_second_preview_replaces_the_first_voice(rig, clock):
    engine, _, store, main, temp = setup(rig, clock, preview_seconds=1.0)
    engine.play(0)
    engine._render(BLOCK)
    engine.play_preview(temp)
    engine._render(BLOCK)
    first = engine.status()["mix_preview"]["seq"]
    engine.play_preview(temp)
    assert engine.status()["mix_preview"]["seq"] > first
    out = engine._render(BLOCK)
    expected = (mixer.mix(main, store, 2 * BLOCK, BLOCK).T
                + mixer.mix(temp, store, 0, BLOCK).T)
    np.testing.assert_allclose(out, expected, atol=1e-6)


def test_the_timeline_stop_takes_the_voice_with_it(rig, clock):
    engine, _, _, _, temp = setup(rig, clock, preview_seconds=1.0)
    engine.play(0)
    engine._render(BLOCK)
    engine.play_preview(temp)
    engine.stop()
    assert engine.status()["mix_preview"] is None
    assert not np.any(engine._render(BLOCK))


def test_preview_while_stopped_still_plays_alone_and_puts_the_playhead_back(rig, clock):
    engine, _, store, _, temp = setup(rig, clock)
    engine.seek(5000)
    engine.play_preview(temp)
    status = engine.status()
    assert status["preview"] is True
    assert status["mix_preview"] is None
    out = engine._render(BLOCK)
    np.testing.assert_array_equal(out, mixer.mix(temp, store, 0, BLOCK).T)
    engine.stop()
    assert engine.status()["position"] == 5000


def test_a_loud_voice_cannot_clip_the_sum(rig, clock):
    store = MemoryStore({"m": tone(440, 4.0, 0.8), "p": tone(1000, 0.2, 3.0)})
    main = project_with({"m": store.arrays["m"]})
    engine = Engine(FakeSession(main, store), background=False, clock=clock)
    engine.play(0)
    engine._render(BLOCK)
    engine.play_preview(project_with({"p": store.arrays["p"]}), limit=True)
    out = engine._render(BLOCK)
    assert np.abs(out).max() <= 1.0
    assert preview_level.soft_limit(np.full((2, 2), 3.0, np.float32)).max() < 1.0


def test_the_voice_plays_at_a_device_rate_that_differs_from_the_project(rig, clock):
    rig.refused_rates = {RATE}
    rig.device_rate = 44100.0
    engine, _, _, _, temp = setup(rig, clock, preview_seconds=1.0)
    engine.play(0)
    engine._render(BLOCK)
    engine.play_preview(temp)
    heard = np.concatenate([engine._render(BLOCK) for _ in range(6)])
    # a 1 kHz tone from the voice must show up in the resampled mix
    spectrum = np.abs(np.fft.rfft(heard[:, 0] * np.hanning(len(heard))))
    freqs = np.fft.rfftfreq(len(heard), 1 / 44100)
    assert spectrum[(freqs > 950) & (freqs < 1050)].max() > 20 * np.median(spectrum)


def test_the_first_block_after_the_call_already_holds_the_voice(rig, clock):
    engine, _, store, main, temp = setup(rig, clock)
    engine.play(0)
    engine._render(BLOCK)
    engine.play_preview(temp)
    out = engine._render(BLOCK)
    voice_only = out - mixer.mix(main, store, BLOCK, BLOCK).T
    assert np.abs(voice_only).max() > 0.1  # at most two blocks; here it is one


class SlowStore(MemoryStore):
    """Reads of the preview's media take 0.3 s (a cold decode)."""

    def read(self, media_id, first, count):
        if media_id == "p":
            time.sleep(0.3)
        return super().read(media_id, first, count)


def test_no_lock_the_audio_thread_or_the_live_channel_needs_is_held_while_it_warms(
        rig, clock):
    engine, _, _, _, temp = setup(rig, clock, store_cls=SlowStore)
    engine.play(0)
    engine._render(BLOCK)
    caller = threading.Thread(target=engine.play_preview, args=(temp,))
    caller.start()
    time.sleep(0.05)  # inside the slow read
    began = time.perf_counter()
    engine.status()  # the live channel's poll takes the control lock
    engine._render(BLOCK)  # the audio callback takes the transport lock
    assert time.perf_counter() - began < 0.1
    caller.join(3)
    assert engine.status()["mix_preview"] is not None
