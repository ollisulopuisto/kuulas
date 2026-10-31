"""Shuttle above 2x plays ~60 ms grains (WP26), no device.

Tape-rate resampling at 3x or 5x turns speech into squeaks; grains keep the
pitch and skip programme between them. The playhead still moves ``speed``
programme frames per output frame, and a run ends where a tape run does.
Nothing here opens a real device or plays a sound.
"""

import numpy as np
import pytest
from test_engine import RATE, Clock, install_rig, make
from test_engine_rate import peak_hz, pull, tone

from kuulas import messages
from kuulas.engine import scrub_speed
from kuulas.scrub_grains import GRAIN_S, XFADE_S


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


@pytest.mark.parametrize("speed", [3.0, 5.0, -3.0, -5.0])
def test_grains_keep_the_pitch(rig, clock, speed):
    engine, _, _ = make(rig, clock, {"m": tone(600, 4.0)})
    engine.play(0 if speed > 0 else 4 * RATE, preserve_pitch=False, rate=speed)
    out = np.concatenate([engine._render(1024) for _ in range(8)])[2048:, 0]
    assert abs(peak_hz(out) - 600) <= 40  # not 1800 or 3000


@pytest.mark.parametrize("speed", [2.5, 3.0, 5.0, -2.5, -5.0])
def test_the_playhead_moves_by_the_speed(rig, clock, speed):
    engine, _, _ = make(rig, clock, {"m": tone(300, 6.0)})
    start = 3 * RATE
    engine.play(start, preserve_pitch=False, rate=speed)
    for _ in range(10):
        engine._render(1000)
    assert abs(engine.status()["position"] - (start + 10000 * speed)) <= 1


@pytest.mark.parametrize("speed", [3.0, 5.0])
def test_forward_grains_run_to_the_end(rig, clock, speed):
    engine, session, _ = make(rig, clock)
    length = session.state.length
    engine.play(0, preserve_pitch=False, rate=speed)
    out = pull(engine)
    assert abs(len(out) - length / speed) <= RATE * 0.12  # a grain of padding
    assert np.isfinite(out).all()
    assert np.abs(out).max() <= 1.0
    assert engine.status()["position"] == length or not engine.status()["playing"]


@pytest.mark.parametrize("speed", [-3.0, -5.0])
def test_backward_grains_play_forward_and_stop_at_zero(rig, clock, speed):
    engine, _, _ = make(rig, clock, {"m": np.arange(
        2 * RATE, dtype=np.float32)[None, :] / (2 * RATE)})  # a rising ramp
    engine.play(2 * RATE - 1, preserve_pitch=False, rate=speed)
    first = engine._render(600)[:, 0]
    assert np.all(np.diff(first[:500]) >= -1e-6)  # one grain: rising, not reversed
    out = pull(engine)
    assert not engine.status()["playing"]
    assert engine.status()["position"] == 0
    assert len(out) > 0


def test_grains_are_continuous_across_blocks(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(200, 6.0)})
    engine.play(0, preserve_pitch=False, rate=3.0)
    blocks = [engine._render(n) for n in [1000, 7, 333, 2048, 1] * 6]
    one = np.concatenate(blocks)
    assert np.isfinite(one).all()
    engine2, _, _ = make(rig, clock, {"m": tone(200, 6.0)})
    engine2.play(0, preserve_pitch=False, rate=3.0)
    again = np.concatenate([engine2._render(1024) for _ in range(10)])
    n = min(len(one), len(again))
    np.testing.assert_allclose(one[:n], again[:n], atol=1e-6)  # block size irrelevant


def test_grain_shuttle_advances_across_skipped_programme_time(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(440, 8.0)})
    engine.play(0, rate=3.0, preserve_pitch=False, skip=[(RATE, 2 * RATE)])
    for _ in range(18):
        engine._render(1024)

    # 18 blocks advance 1.152 s of played audio at 3x, plus the skipped second.
    assert engine.status()["position"] == pytest.approx(2.152 * RATE, abs=4)


def test_short_project_grain_shuttle_stops_at_its_last_frame(rig, clock):
    engine, session, _ = make(rig, clock, {"m": tone(330, 0.11)})
    engine.play(0, rate=5.0, preserve_pitch=False)
    rendered = 0
    while engine.status()["playing"] and rendered < 10_000:
        engine._render(256)
        rendered += 256

    # A project shorter than one grain still plays one grain at normal pitch.
    # Include that minimum grain and the final device-block rounding.
    grain_step = round(GRAIN_S * RATE) - round(XFADE_S * RATE)
    assert rendered == pytest.approx(max(session.state.length / 5, grain_step), abs=256)
    assert not engine.status()["playing"]
    assert engine.status()["position"] == session.state.length


def test_2x_and_below_still_resample(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(600, 4.0)})
    engine.play(0, preserve_pitch=False, rate=2.0)
    out = np.concatenate([engine._render(1024) for _ in range(12)])[2048:, 0]
    assert abs(peak_hz(out) - 1200) <= 8


def test_a_velocity_scrub_plays_in_the_direction_and_speed_of_the_drag(rig, clock):
    assert scrub_speed(None) is None
    assert scrub_speed(float("nan")) is None
    assert scrub_speed(0.1) is None  # too slow: the fixed burst
    assert scrub_speed(-0.1) is None
    assert scrub_speed(1.5) == 1.5
    assert scrub_speed(-3.0) == -3.0
    assert scrub_speed(40.0) == 5.0  # capped at the fastest shuttle
    assert scrub_speed(-40.0) == -5.0
    engine, _, _ = make(rig, clock, {"m": tone(300, 6.0)})
    engine.scrub(3 * RATE, velocity=-4.0)
    status = engine.status()
    assert status["playing"]
    assert status["speed"] == -4.0
    out = np.concatenate([engine._render(1024) for _ in range(5)])
    assert np.abs(out).max() > 0.1
    assert not engine.status()["playing"]  # the burst ended by itself


def test_a_scrub_without_velocity_is_the_fixed_burst(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(300, 6.0)})
    engine.scrub(3 * RATE)
    assert engine.status()["speed"] == 1.0
    engine2, _, _ = make(rig, clock, {"m": tone(300, 6.0)})
    engine2.scrub(3 * RATE, velocity=0.05)
    assert engine2.status()["speed"] == 1.0
