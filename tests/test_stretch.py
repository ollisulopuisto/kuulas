"""The WSOLA stretcher (WP26) on synthetic signals, no engine, no device."""

import time

import numpy as np
import pytest

from kuulas.stretch import Stretcher

RATE = 48000


def tone(hz: float, seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    one = (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    return np.stack([one, one])


def voice(seconds: float, f0: float = 110.0) -> np.ndarray:
    """A vowel-like signal: a few harmonics of a gliding f0 under a syllable
    envelope, so grains are not all alike."""
    t = np.arange(round(seconds * RATE)) / RATE
    f = f0 * (1 + 0.1 * np.sin(2 * np.pi * 0.7 * t))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    x = sum(np.sin(k * phase) / k for k in range(1, 6))
    x = x * (0.6 + 0.4 * np.sin(2 * np.pi * 3.0 * t))
    x = (0.3 * x / np.abs(x).max()).astype(np.float32)
    return np.stack([x, x])


def source(data: np.ndarray):
    return lambda first, count: data[:, first:first + count]


def run(data: np.ndarray, speed: float, *, hops=None, change=None) -> np.ndarray:
    """All of ``data`` through the stretcher at ``speed``. ``change`` maps a
    hop number to a new speed."""
    s = Stretcher(source(data), data.shape[1], RATE, speed)
    out, n = [], 0
    while not s.finished and (hops is None or n < hops):
        if change and n in change:
            s.set_speed(change[n])
        block = s.next_hop()
        if block is None:
            break
        out.append(block)
        n += 1
    return np.concatenate(out).T


def peak_hz(x: np.ndarray) -> float:
    window = np.hanning(len(x))
    spectrum = np.abs(np.fft.rfft(x * window))
    return float(np.argmax(spectrum) * RATE / len(x))


@pytest.mark.parametrize("speed", [1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 3.0, 0.75])
def test_the_length_is_the_input_over_the_speed(speed):
    data = voice(6.0)
    out = run(data, speed)
    assert out.shape[1] == pytest.approx(data.shape[1] / speed, rel=0.02)


@pytest.mark.parametrize("speed", [1.0, 1.1, 1.37, 1.5, 2.0])
@pytest.mark.parametrize("hz", [220.0, 440.0, 1000.0])
def test_a_sine_keeps_its_frequency(speed, hz):
    out = run(tone(hz, 4.0), speed)[0]
    middle = out[RATE // 4:-RATE // 4]
    assert abs(peak_hz(middle) - hz) <= 0.01 * hz


@pytest.mark.parametrize("speed", [1.2, 1.5, 2.0])
def test_a_sine_keeps_its_level_and_has_no_clicks_at_the_joins(speed):
    data = tone(440.0, 3.0, amp=0.5)
    out = run(data, speed)[0]
    middle = out[RATE // 4:-RATE // 4]
    own_step = float(np.abs(np.diff(data[0])).max())
    # A join that is off by even a few frames of phase steps well past the
    # tone's own steepest slope; 1.15 leaves room for the overlap's rounding.
    assert float(np.abs(np.diff(middle)).max()) <= 1.15 * own_step
    assert float(np.abs(middle).max()) == pytest.approx(0.5, abs=0.03)


@pytest.mark.parametrize("speed", [1.1, 1.5, 1.85])
def test_grains_join_in_phase_so_the_level_does_not_dip(speed):
    """Out-of-phase overlaps cancel: a tone's level would pulse at the hop
    rate. In phase it stays within 10 percent of its mean over 5 ms windows."""
    out = run(tone(330.0, 4.0), speed)[0]
    middle = out[RATE // 4:-RATE // 4]
    win = RATE // 200
    rms = np.sqrt((middle[:len(middle) // win * win].reshape(-1, win) ** 2).mean(axis=1))
    assert float(rms.min()) >= 0.9 * float(rms.mean())
    assert float(rms.max()) <= 1.1 * float(rms.mean())


def test_no_clicks_on_a_voice_like_signal():
    data = voice(5.0)
    own_step = float(np.abs(np.diff(data[0])).max())
    out = run(data, 1.6)[0]
    assert float(np.abs(np.diff(out[RATE // 4:-RATE // 4])).max()) <= 1.5 * own_step


def test_the_speed_can_change_every_hop_without_a_click():
    data = tone(300.0, 4.0)
    own_step = float(np.abs(np.diff(data[0])).max())
    # A sweep 1.0 -> 2.0 -> 1.0 in 0.05 steps, one step per hop, then held.
    ramp = {i: 1.0 + 0.05 * min(i, 40 - i) for i in range(41)}
    out = run(data, 1.0, change=ramp)[0]
    middle = out[RATE // 8:-RATE // 4]
    assert float(np.abs(np.diff(middle)).max()) <= 1.15 * own_step
    assert abs(peak_hz(middle) - 300.0) <= 3.0


def test_a_sudden_change_of_speed_keeps_pitch_and_continuity():
    data = tone(500.0, 4.0)
    own_step = float(np.abs(np.diff(data[0])).max())
    out = run(data, 1.0, change={50: 2.0, 100: 1.2})[0]
    assert float(np.abs(np.diff(out[RATE // 8:-RATE // 4])).max()) <= 1.15 * own_step


def test_the_position_advances_by_hop_times_speed():
    data = voice(3.0)
    s = Stretcher(source(data), data.shape[1], RATE, 1.5)
    for _ in range(10):
        s.next_hop()
    assert s.position == pytest.approx(10 * s.hop * 1.5)


def test_input_is_read_once_and_only_a_little_ahead():
    data = voice(3.0)
    seen = []

    def fetch(first, count):
        seen.append((first, count))
        return data[:, first:first + count]

    s = Stretcher(fetch, data.shape[1], RATE, 1.5)
    for _ in range(50):
        s.next_hop()
    assert sum(c for _, c in seen) <= 50 * s.hop * 1.5 + 6 * s.hop


def test_the_stream_ends_with_the_input_and_then_returns_none():
    data = tone(440.0, 0.5)
    s = Stretcher(source(data), data.shape[1], RATE, 1.5)
    blocks = 0
    while (block := s.next_hop()) is not None:
        blocks += 1
        assert block.shape == (s.hop, 2)
        assert blocks < 1000
    assert s.finished
    assert s.next_hop() is None


def test_stereo_channels_stay_separate():
    left, right = tone(300.0, 2.0)[0], tone(900.0, 2.0)[0]
    data = np.stack([left, right])
    out = run(data, 1.4)
    middle = slice(RATE // 4, -RATE // 4)
    assert abs(peak_hz(out[0][middle]) - 300.0) <= 3.0
    assert abs(peak_hz(out[1][middle]) - 900.0) <= 9.0


def test_a_hop_is_cheap():
    """Self-relative: a hop must cost far less than the 20 ms it covers. The
    callback budget is about 3 ms per block; this allows 3 ms per hop with a
    margin for a loaded machine, where the measured cost is about 0.2 ms."""
    data = voice(10.0)
    s = Stretcher(source(data), data.shape[1], RATE, 1.8)
    times = []
    for _ in range(300):
        began = time.perf_counter()
        s.next_hop()
        times.append(time.perf_counter() - began)
    assert float(np.median(times)) < 0.003
    assert float(np.percentile(times, 99)) < 0.010
