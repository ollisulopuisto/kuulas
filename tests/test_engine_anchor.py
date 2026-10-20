"""The playhead anchor, instant stop and the output buffer (precise cursor), no device.

The browser draws the playhead by extrapolating from an anchor: a position, the
monotonic time it was heard, the speed and a sequence number that changes on
every transport change. Stopping or jumping must silence what the device has
already queued (the stream is aborted, and started again cheaply). Nothing here
opens a real device or plays a sound: ``FakeStream`` from ``test_engine``.
"""

from types import SimpleNamespace

import numpy as np
import pytest
import sounddevice as sd
from test_engine import RATE, Clock, install_rig, make, noise

from kuulas import messages


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


def counting(stream):
    """Count the stream's aborts and starts (the fake does not)."""
    stream.aborts, stream.starts = 0, 0
    abort, start = stream.abort, stream.start

    def counted_abort():
        stream.aborts += 1
        abort()

    def counted_start():
        stream.starts += 1
        start()

    stream.abort, stream.start = counted_abort, counted_start
    return stream


# -- the anchor ----------------------------------------------------------------


def test_status_dates_the_position_to_the_callback_that_produced_it(rig, clock):
    rig.latency = 0.01  # 480 frames
    engine, _, _ = make(rig, clock)
    engine.play(0)
    for _ in range(4):
        clock.now += 1024 / RATE
        rig.stream.pump()
    heard_at = clock.now
    clock.now += 0.015  # the status is read later than the last callback
    status = engine.status()
    assert status["position"] == 4096 - 480
    assert status["t"] == pytest.approx(heard_at)


def test_before_anything_is_heard_the_anchor_is_dated_when_it_will_be(rig, clock):
    rig.latency = 0.02  # 960 frames: the first block is heard 20 ms after it is made
    engine, _, _ = make(rig, clock)
    engine.play(1000)
    started = clock.now
    status = engine.status()
    assert status["position"] == 1000
    assert status["t"] == pytest.approx(started + 0.02)


def test_status_says_where_the_run_ends(rig, clock):
    engine, session, _ = make(rig, clock, {"m": noise(1)})
    engine.play(0)
    assert engine.status()["end"] == session.state.length
    engine.play(0, until=5000)
    assert engine.status()["end"] == 5000
    engine.play(9000, rate=-1.0)
    assert engine.status()["end"] == 0


def test_the_sequence_changes_with_every_transport_change(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(3)})
    seen = [engine.status()["seq"]]

    def changed():
        seq = engine.status()["seq"]
        assert seq > seen[-1]
        seen.append(seq)

    engine.play(0)
    changed()
    engine.seek(RATE)
    changed()
    engine.play(rate=1.5)  # a stretch run
    changed()
    assert engine.set_rate(1.7)
    changed()
    engine.stop()
    changed()
    engine.play(0, until=1000)
    changed()
    engine._render(2048)  # runs out by itself
    assert not engine.status()["playing"]
    changed()
    before = engine.status()["seq"]
    clock.now += 1
    rig.stream.pump()  # stopped: nothing changes
    assert engine.status()["seq"] == before


# -- instant stop ------------------------------------------------------------------


def test_stop_while_playing_silences_what_the_device_has_queued(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    stream = counting(rig.stream)
    rig.stream.pump()
    engine.stop()
    assert stream.aborts == 1  # the device's queue is dropped, not played out
    assert not stream.closed  # kept for the next play: start is cheap, open is not
    engine._tick()
    assert "notice.engine.device_changed" not in [
        n["key"] for n in engine.status()["notices"]]  # our own abort is no failure
    assert len(rig.streams) == 1
    engine.play()
    assert stream.starts == 1
    assert stream.active
    assert len(rig.streams) == 1
    assert rig.stream.pump().any()


def test_stop_while_stopped_leaves_the_stream_alone(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0, until=100)
    stream = counting(rig.stream)
    rig.stream.pump()  # ran out
    engine.stop()
    assert stream.aborts == 0


def test_a_parked_stream_that_will_not_start_is_opened_afresh(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    rig.stream.pump()
    engine.stop()
    old = rig.stream

    def refuse():
        raise sd.PortAudioError("Internal PortAudio error", -9986)

    old.start = refuse
    engine.play()
    assert len(rig.streams) == 2
    assert old.closed
    assert rig.stream.active
    assert engine.status()["playing"]


def test_a_seek_while_playing_drops_the_old_audio_and_plays_on(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(3)})
    engine.play(0)
    stream = counting(rig.stream)
    rig.stream.pump()
    engine.seek(2 * RATE)
    assert stream.aborts == 1
    assert stream.starts == 1
    assert stream.active
    assert engine.status()["playing"]


def test_a_tiny_seek_or_a_speed_change_in_place_keeps_the_stream_running(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(3)})
    engine.play(0)
    stream = counting(rig.stream)
    for _ in range(4):
        rig.stream.pump()
    heard = engine.status()["position"]
    engine.seek(heard + 48)  # 1 ms: a nudge, not a jump
    engine.play(heard + 48, rate=2.0, preserve_pitch=False)  # J/K/L from where it is
    assert stream.aborts == 0


def test_a_seek_while_stopped_does_not_touch_the_stream(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    rig.stream.pump()
    engine.stop()
    stream = counting(rig.stream)
    engine.seek(5000)
    assert stream.aborts == 0
    assert stream.starts == 0


# -- the output buffer and its numbers -------------------------------------------------


def test_the_stream_asks_for_low_latency_then_high_with_a_bigger_block_when_late(
        rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0)
    assert rig.stream.kwargs["latency"] == "low"
    rig.stream.pump(underflow=True)
    rig.stream.pump(underflow=True)
    engine._tick()
    assert rig.stream.kwargs["latency"] == "high"
    assert rig.stream.blocksize == 2048
    assert engine.status()["latency"]["setting"] == "high"


def test_status_reports_the_latency_numbers(rig, clock):
    rig.latency = 0.035
    engine, _, _ = make(rig, clock)
    engine.play(0)
    stream = rig.stream
    for i in range(6):
        clock.now += 1024 / RATE
        when = SimpleNamespace(outputBufferDacTime=10.0 + i + 0.015, currentTime=10.0 + i)
        stream.callback(stream_out(), 1024, when, SimpleNamespace(output_underflow=False))
    numbers = engine.status()["latency"]
    assert numbers["setting"] == "low"
    assert numbers["stream_ms"] == pytest.approx(35.0)
    assert numbers["block_ms"] == pytest.approx(1024 / RATE * 1000, abs=0.01)
    assert numbers["dac_lead_ms"] == pytest.approx(15.0, abs=0.01)
    assert numbers["callback_ms"] == pytest.approx(1024 / RATE * 1000, abs=0.01)
    assert numbers["jitter_ms"] == pytest.approx(0.0, abs=0.01)
    # the playhead subtracts the stream's figure; the device's timing says block + lead
    assert numbers["estimate_ms"] == pytest.approx(35.0)
    assert numbers["measured_ms"] == pytest.approx(1024 / RATE * 1000 + 15.0, abs=0.01)


def stream_out():
    return np.zeros((1024, 2), dtype=np.float32)
