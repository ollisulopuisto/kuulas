"""Tape-rate playback (WP26: JKL shuttle, pitch follows speed), no device.

``play(at, rate=r, preserve_pitch=False)`` resamples the mix so that ``r``
programme frames pass per output frame: faster is higher, slower is lower,
negative is backward. The streaming resampler is soxr, the one the engine
already uses for devices that cannot run the project rate. The tests pull
blocks from the engine and compare them with a one-shot soxr resampling of
the whole mix, check that a tone comes out at ``r`` times its frequency
(independent of soxr), and that the playhead moves ``r`` frames per frame.
Pitch-kept playback is in test_engine_stretch.py.
Above 2x the shuttle plays grains instead (test_engine_grains.py).
Nothing here opens a real device or plays a sound.
"""

import numpy as np
import pytest
import soxr
from test_engine import (
    RATE,
    Clock,
    FakeSession,
    MemoryStore,
    install_rig,
    make,
    noise,
    project_with,
)

from kuulas import messages, mixer
from kuulas.engine import Engine
from kuulas.messages import KuulasError
from kuulas.playplan import PlaybackRequestError

LADDER = (0.25, 1.5, 2.0, 3.0, 5.0)
SIZES = [1000, 333, 1024, 7, 2048]


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


def pull(engine, sizes=SIZES, limit=20_000) -> np.ndarray:
    blocks = []
    while engine.status()["playing"] and len(blocks) < limit:
        blocks.append(engine._render(sizes[len(blocks) % len(sizes)]))
    assert not engine.status()["playing"], "playback never ended"
    return np.concatenate(blocks)


def tone(hz: float, seconds: float = 2.0) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    return (0.5 * np.sin(2 * np.pi * hz * t))[None, :].astype(np.float32)


def peak_hz(x: np.ndarray, rate: float = RATE) -> float:
    window = np.hanning(len(x))
    spectrum = np.abs(np.fft.rfft(x * window))
    return float(np.argmax(spectrum) * rate / len(x))


def tape(engine, at=0, **kwargs):
    engine.play(at, preserve_pitch=False, **kwargs)


@pytest.mark.parametrize("speed", [v for v in LADDER if v <= 2.0])
def test_tape_rate_matches_a_reference_resampling(rig, clock, speed):
    engine, session, store = make(rig, clock)  # 2 s of noise
    length = session.state.length
    tape(engine, rate=speed)
    out = pull(engine)
    whole = mixer.mix(session.state, store, 0, length).T
    expected = soxr.resample(whole, speed * RATE, RATE, quality="HQ")
    assert abs(len(expected) - length / speed) <= 1
    n = len(expected)
    # Streaming and one-shot soxr agree to well below audibility; after the
    # end there is only the silence that pads the last block.
    np.testing.assert_allclose(out[:n - 2], expected[:n - 2], rtol=0, atol=1e-4)
    assert not out[n + 2:].any()


@pytest.mark.parametrize("speed", [0.25, 1.5, 2.0, -1.0, -1.5])
def test_pitch_follows_the_speed(rig, clock, speed):
    engine, _, _ = make(rig, clock, {"m": tone(600, 4.0)})
    start = 0 if speed > 0 else 4 * RATE
    tape(engine, at=start, rate=speed)
    out = np.concatenate([engine._render(1024) for _ in range(12)])[2048:, 0]
    assert abs(peak_hz(out) - 600 * abs(speed)) <= 8


@pytest.mark.parametrize("speed", [0.25, 1.5, 2.0, -1.0, -2.0, 5.0])
def test_the_playhead_moves_by_the_speed(rig, clock, speed):
    engine, _, _ = make(rig, clock, {"m": noise(6)})
    start = 3 * RATE
    tape(engine, at=start, rate=speed)
    for _ in range(10):
        engine._render(1000)
    assert abs(engine.status()["position"] - (start + 10000 * speed)) <= 1
    assert engine.status()["speed"] == speed


def test_reverse_at_1x_is_the_mix_backwards_exactly(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(30000, rate=-1.0)  # 1x backwards keeps its pitch: no flag needed
    out = pull(engine)
    expected = mixer.mix(session.state, store, 0, 30000).T[::-1]
    assert out.shape[0] >= 30000
    np.testing.assert_allclose(out[:30000], expected, rtol=0, atol=1e-6)
    assert not out[30000:].any()
    status = engine.status()
    assert not status["playing"]
    assert status["position"] == 0


def test_reverse_stops_at_until_below_the_start(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(30000, until=10000, rate=-1.0)
    out = pull(engine)
    expected = mixer.mix(session.state, store, 10000, 20000).T[::-1]
    np.testing.assert_allclose(out[:20000], expected, rtol=0, atol=1e-6)
    assert engine.status()["position"] == 10000


def test_fast_reverse_is_a_resampling_of_the_reversed_mix(rig, clock):
    engine, session, store = make(rig, clock)
    tape(engine, at=60000, rate=-2.0)
    out = pull(engine)
    backwards = np.ascontiguousarray(mixer.mix(session.state, store, 0, 60000).T[::-1])
    expected = soxr.resample(backwards, 2 * RATE, RATE, quality="HQ")
    n = len(expected)
    np.testing.assert_allclose(out[:n - 2], expected[:n - 2], rtol=0, atol=1e-4)
    assert not out[n + 2:].any()
    assert engine.status()["position"] == 0


def test_reverse_with_a_skip_jumps_it_on_the_way_back(rig, clock):
    engine, session, store = make(rig, clock)
    engine.play(60000, rate=-1.0, skip=[(20000, 40000)])
    blocks = [engine._render(1000) for _ in range(19)]
    assert engine.status()["position"] == 41000
    blocks.append(engine._render(2000))
    assert engine.status()["position"] == 19000
    out = np.concatenate([*blocks, pull(engine)])
    assert engine.status()["position"] == 0
    tail = mixer.mix(session.state, store, 40000, 20000).T[::-1]
    head = mixer.mix(session.state, store, 0, 20000).T[::-1]
    # Away from the join (15 ms wide at most) each side is the mix backwards.
    np.testing.assert_allclose(out[:20000 - 400], tail[:-400], rtol=0, atol=1e-6)
    np.testing.assert_allclose(out[20000 + 400:40000], head[400:], rtol=0, atol=1e-6)
    assert not out[40000:].any()


def test_tape_rate_with_a_skip_plays_the_pieces_faster(rig, clock):
    engine, session, _ = make(rig, clock)
    length = session.state.length
    tape(engine, rate=2.0, skip=[(20000, 40000)])
    for _ in range(10):
        engine._render(1000)  # 20000 programme frames: right at the join
    assert engine.status()["position"] == 40000
    # One frame at a time: no silence padding the end.
    rest = pull(engine, sizes=[1], limit=100_000)
    assert abs(10000 + len(rest) - (length - 20000) / 2) <= 2


def test_tape_rate_through_the_device_resampler_too(rig, clock):
    rig.refused_rates = {RATE}
    rig.device_rate = 44100.0
    arrays = {"m": tone(600, 4.0)}
    engine = Engine(FakeSession(project_with(arrays), MemoryStore(arrays)),
                    background=False, clock=clock)
    tape(engine, rate=1.5)
    out = np.concatenate([rig.stream.pump(441) for _ in range(100)])  # 1 s
    assert abs(peak_hz(out[4410:, 0], 44100) - 900) <= 8
    assert abs(engine.status()["position"] - 1.5 * RATE) <= 2


def test_a_seek_keeps_the_speed(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(6)})
    tape(engine, rate=2.0)
    engine._render(1000)
    engine.seek(RATE)
    for _ in range(5):
        engine._render(1000)
    assert engine.status()["position"] == RATE + 10000


@pytest.mark.parametrize("speed", [-1.5, 0.0, 0.3, 3.5, float("nan")])
def test_keeping_the_pitch_outside_forward_0_5_to_3_is_refused(rig, clock, speed):
    """Pitch-kept playback (WP26, stretch.py) exists forward from 0.5x to 3x;
    this was "refused for now" for every speed before it was built."""
    engine, _, _ = make(rig, clock)
    with pytest.raises(KuulasError) as caught:
        engine.play(0, rate=speed)  # preserve_pitch defaults to True
    assert caught.value.key in ("error.engine.stretch_unavailable",
                                "error.engine.bad_speed")
    assert str(caught.value) != caught.value.key  # translated
    assert not engine.status()["playing"]
    assert rig.streams == []  # nothing was opened, nothing pitch-shifted


@pytest.mark.parametrize("speed", [0.0, 0.1, 6.0, float("nan"), float("inf"), -10.0])
def test_a_speed_off_the_ladder_range_is_refused(rig, clock, speed):
    engine, _, _ = make(rig, clock)
    with pytest.raises(PlaybackRequestError) as caught:
        engine.play(0, rate=speed, preserve_pitch=False)
    assert caught.value.key == "error.engine.bad_speed"
    assert not engine.status()["playing"]


def test_the_callback_at_tape_rate_never_raises(rig, clock):
    engine, _, _ = make(rig, clock)
    tape(engine, rate=-3.0, at=90000)
    out = np.concatenate([rig.stream.pump(n) for n in [1024, 1, 1023, 4096] * 20])
    assert np.isfinite(out).all()
    assert engine.status()["failed_blocks"] == 0
    assert not engine.status()["playing"]
