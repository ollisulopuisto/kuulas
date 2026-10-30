"""WP26: grain renderer for shuttle speeds above 2x (60 ms grains with a skip)."""

from __future__ import annotations

import numpy as np
import pytest

from kuulas.scrub_grains import GRAIN_S, XFADE_S, render_grains

RATE = 48000


def _ramp(n: int) -> np.ndarray:
    """A stereo mix whose value is the frame index, so positions can be read back."""
    x = np.arange(n, dtype=np.float32)
    return np.stack([x, x], axis=1)


def _read(mix):
    def read(first: int, count: int) -> np.ndarray:
        out = np.zeros((count, 2), dtype=np.float32)
        lo, hi = max(first, 0), min(first + count, len(mix))
        if hi > lo:
            out[lo - first:hi - first] = mix[lo:hi]
        return out
    return read


def test_output_has_the_requested_length_and_advances_by_speed():
    out, end = render_grains(_read(_ramp(RATE * 20)), start=RATE, speed=5.0,
                             frames=RATE, rate=RATE)
    assert out.shape == (RATE, 2)
    # one second of output at 5x moves the programme position by five seconds
    assert end == pytest.approx(RATE + 5 * RATE, abs=RATE * 0.01)


def test_grains_are_one_grain_long_with_a_skip_between_them():
    out, _ = render_grains(_read(_ramp(RATE * 20)), start=RATE, speed=4.0,
                           frames=RATE // 2, rate=RATE, fade=False)
    grain = round(GRAIN_S * RATE)
    first, second = out[:grain, 0], out[grain:2 * grain, 0]
    assert np.all(np.diff(first) == 1.0)          # a grain plays at 1x (pitch kept)
    assert second[0] - first[0] == pytest.approx(grain * 4.0, abs=2)  # then skips


def test_backward_grains_move_the_position_back_and_play_forward():
    out, end = render_grains(_read(_ramp(RATE * 20)), start=RATE * 10, speed=-3.0,
                             frames=RATE, rate=RATE, fade=False)
    assert end == pytest.approx(RATE * 10 - 3 * RATE, abs=RATE * 0.01)
    grain = round(GRAIN_S * RATE)
    assert np.all(np.diff(out[:grain, 0]) == 1.0)     # each grain itself is not reversed
    assert out[grain, 0] < out[0, 0]                  # but the next grain is earlier


def test_joins_have_no_jump_larger_than_the_signal():
    t = np.arange(RATE * 20) / RATE
    tone = np.sin(2 * np.pi * 220 * t).astype(np.float32)
    mix = np.stack([tone, tone], axis=1)
    out, _ = render_grains(_read(mix), start=RATE, speed=5.0, frames=RATE, rate=RATE)
    step = np.abs(np.diff(out[:, 0]))
    assert step.max() <= 2 * np.abs(np.diff(tone)).max() + 1e-6
    assert np.isfinite(out).all()
    assert np.abs(out).max() <= 1.0 + 1e-6


def test_crossfade_is_shorter_than_a_grain():
    assert 0 < XFADE_S < GRAIN_S / 2


def test_reads_outside_the_mix_are_silence_not_errors():
    out, _ = render_grains(_read(_ramp(1000)), start=500, speed=5.0,
                           frames=RATE // 4, rate=RATE)
    assert out.shape == (RATE // 4, 2)
    assert np.isfinite(out).all()


def test_rejects_speeds_the_grain_renderer_does_not_serve():
    with pytest.raises(ValueError, match=r"least|zero"):
        render_grains(_read(_ramp(1000)), start=0, speed=1.0, frames=10, rate=RATE)
    with pytest.raises(ValueError, match=r"zero|least"):
        render_grains(_read(_ramp(1000)), start=0, speed=0.0, frames=10, rate=RATE)
