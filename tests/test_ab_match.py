"""Level matching for A/B (WP24.2)."""

import numpy as np

from kuulas.ab_match import match_gains

RATE = 48_000


def _tone(amplitude: float, seconds: float = 1.0, channels: int = 2) -> np.ndarray:
    t = np.arange(int(RATE * seconds), dtype=np.float32) / np.float32(RATE)
    wave = (amplitude * np.sin(2.0 * np.pi * 1000.0 * t)).astype(np.float32)
    return np.broadcast_to(wave, (channels, wave.shape[0])).copy()


def test_six_db_apart_turns_the_louder_side_down():
    a = _tone(0.5)
    b = _tone(0.5 / 10 ** (6.0 / 20.0))
    gain_a, gain_b = match_gains(a, b, RATE)
    assert gain_b == 0.0
    assert abs(gain_a - (-6.0)) <= 0.3


def test_louder_side_b_turns_down_instead():
    a = _tone(0.5 / 10 ** (6.0 / 20.0))
    b = _tone(0.5)
    gain_a, gain_b = match_gains(a, b, RATE)
    assert gain_a == 0.0
    assert abs(gain_b - (-6.0)) <= 0.3


def test_equal_tones_give_zero_gain():
    tone = _tone(0.5)
    assert match_gains(tone, tone, RATE) == (0.0, 0.0)
    assert match_gains(_tone(0.5), _tone(0.5), RATE) == (0.0, 0.0)


def test_silent_side_gives_zero_gain():
    a = _tone(0.5)
    silent = np.zeros((2, RATE), dtype=np.float32)
    assert match_gains(a, silent, RATE) == (0.0, 0.0)
    assert match_gains(silent, a, RATE) == (0.0, 0.0)


def test_too_short_to_measure_gives_zero_gain():
    a = _tone(0.5)
    short = np.zeros((2, 100), dtype=np.float32)
    assert match_gains(a, short, RATE) == (0.0, 0.0)


def test_twenty_db_diff_is_capped_at_twelve_db():
    a = _tone(0.5)
    b = _tone(0.5 / 100.0)
    gain_a, gain_b = match_gains(a, b, RATE)
    assert gain_b == 0.0
    assert abs(gain_a - (-12.0)) <= 0.3


def test_mono_and_stereo_inputs_both_work():
    a = _tone(0.5, channels=1)
    b = _tone(0.5 / 10 ** (6.0 / 20.0), channels=1)
    gain_a, gain_b = match_gains(a, b, RATE)
    assert gain_b == 0.0
    assert abs(gain_a - (-6.0)) <= 0.3
    gain_a, gain_b = match_gains(_tone(0.5), _tone(0.25), RATE)
    assert gain_b == 0.0
    assert abs(gain_a - (-6.0)) <= 0.3
