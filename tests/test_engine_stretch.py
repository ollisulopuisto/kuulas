"""Fast listening with the pitch kept, through the engine (WP26), no device.

The stretcher itself is tested on synthetic signals in test_stretch.py. Here:
the engine plays the mix through it, the playhead moves in programme time,
the speed can be changed while playing without a click, and a block costs
about what a block of plain playback costs.
"""

import time

import numpy as np
import pytest
from test_engine import (
    Clock,
    FakeSession,
    MemoryStore,
    install_rig,
    make,
    noise,
    project_with,
)
from test_engine_rate import RATE, peak_hz, tone

from kuulas import messages
from kuulas.engine import Engine
from kuulas.messages import KuulasError


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


def blocks(engine, count, size=1024):
    return np.concatenate([engine._render(size) for _ in range(count)])


def test_fast_playback_keeps_pitch(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(440, 6.0)})
    engine.play(0, rate=1.5)
    out = blocks(engine, 60)[RATE // 2:, 0]
    assert abs(peak_hz(out) - 440) <= 4


def test_fast_playback_advances_programme_time_by_rate(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(8)})
    engine.play(RATE, rate=1.5)
    blocks(engine, 40)
    status = engine.status()
    assert status["speed"] == 1.5
    assert status["position"] == pytest.approx(RATE + 40 * 1024 * 1.5, rel=0.03)


def test_chunk_joins_have_no_discontinuity(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(330, 6.0)})
    engine.play(0, rate=1.7)
    out = blocks(engine, 80, size=777)[:, 0]
    own = float(np.abs(np.diff(tone(330, 1.0)[0])).max())
    assert float(np.abs(np.diff(out[2000:])).max()) <= 1.2 * own


def test_it_plays_to_the_end_and_stops(rig, clock):
    engine, session, _ = make(rig, clock, {"m": tone(300, 3.0)})
    engine.play(0, rate=2.0)
    seen = 0
    while engine.status()["playing"] and seen < 400:
        engine._render(1024)
        seen += 1
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == session.state.length
    assert seen * 1024 == pytest.approx(session.state.length / 2.0, rel=0.1)


def test_set_rate_changes_the_speed_while_playing_without_a_click(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(300, 12.0)})
    engine.play(0, rate=1.0 + 0.05)
    out = [blocks(engine, 10)]
    run_before = engine._run
    for rate in (1.1, 1.35, 1.8, 2.0, 1.5, 1.05):
        assert engine.set_rate(rate) is True
        out.append(blocks(engine, 8))
        assert engine.status()["speed"] == rate
    assert engine._run is run_before  # the same run: nothing was restarted
    joined = np.concatenate(out)[:, 0]
    own = float(np.abs(np.diff(tone(300, 1.0)[0])).max())
    assert float(np.abs(np.diff(joined[2000:])).max()) <= 1.2 * own
    assert abs(peak_hz(joined[-RATE // 4:]) - 300) <= 6


def test_set_rate_when_not_stretching_changes_nothing(rig, clock):
    engine, _, _ = make(rig, clock)
    assert engine.set_rate(1.5) is False  # stopped
    engine.play(0)  # plain 1x
    assert engine.set_rate(1.5) is False
    assert engine.status()["speed"] == 1.0
    engine.play(0, rate=1.5)
    with pytest.raises(KuulasError):
        engine.set_rate(7.0)
    assert engine.set_rate(1.2) is True


def test_the_playhead_follows_a_changed_rate(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(30)})
    engine.play(0, rate=1.2)
    blocks(engine, 20)
    p1 = engine.status()["position"]
    engine.set_rate(2.0)
    blocks(engine, 40)  # the stretcher takes the new speed within a hop or two
    p2 = engine.status()["position"]
    assert (p2 - p1) == pytest.approx(40 * 1024 * 2.0, rel=0.05)


def test_a_skip_is_jumped_in_fast_listening_too(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(6)})
    engine.play(0, rate=1.5, skip=[(RATE, 2 * RATE)])
    while engine.status()["playing"]:
        engine._render(1024)
    assert engine.status()["position"] == 6 * RATE


def test_a_seek_keeps_fast_listening(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(440, 8.0)})
    engine.play(0, rate=1.5)
    blocks(engine, 5)
    engine.seek(4 * RATE)
    out = blocks(engine, 40)[RATE // 2:, 0]
    assert abs(peak_hz(out) - 440) <= 4
    assert engine.status()["speed"] == 1.5
    assert engine.status()["position"] > 4 * RATE


def test_through_a_44100_device_the_pitch_is_still_kept(rig, clock):
    rig.device_rate = 44100.0
    rig.refused_rates = {RATE}
    engine, _, _ = make(rig, clock, {"m": tone(440, 6.0)})
    engine.play(0, rate=1.5)
    out = blocks(engine, 60)[44100 // 2:, 0]
    assert abs(peak_hz(out, 44100) - 440) <= 4.5


def test_the_callback_never_raises_in_fast_listening(rig, clock):
    engine, _, _ = make(rig, clock)
    engine.play(0, rate=1.6)
    out = np.concatenate([rig.stream.pump(n) for n in [1024, 1, 1023, 4096] * 20])
    assert np.isfinite(out).all()
    assert engine.status()["failed_blocks"] == 0


def test_fast_listening_costs_a_block_about_what_a_plain_block_costs(rig, clock):
    """Self-relative and generous: the aim is 3 ms for a 21 ms block, the
    budget here is 4 times plain playback plus 3 ms (measured: about 1 ms
    against 0.1 ms plain with four tracks on an M1)."""
    arrays = {f"m{i}": noise(60, channels=1 + i % 2, seed=i) for i in range(4)}

    def timings(rate):
        engine = Engine(FakeSession(project_with(arrays), MemoryStore(arrays)),
                        background=False, clock=Clock())
        engine.play(0, rate=rate)
        engine._tick()
        times = []
        for i in range(250):
            if i % 12 == 0:
                engine._prefetch()
            began = time.perf_counter()
            engine._render(1024)
            times.append((time.perf_counter() - began) * 1e3)
        engine.close()
        return np.array(times[20:])

    plain, fast = timings(1.0), timings(1.8)
    assert np.percentile(fast, 99) <= 4 * np.percentile(plain, 99) + 3.0
    assert np.median(fast) <= 4 * np.median(plain) + 3.0
