"""Tests for clip loudness measurement and gain calculation (WP19c)."""

from __future__ import annotations

import numpy as np
import pytest

from kuulas.model import Clip
from kuulas.ops import CLIP_GAIN_RANGE

# Will be imported once module is created
try:
    from kuulas.loudness import gain_to_target, measure_clip
except ImportError:
    measure_clip = None  # type: ignore[assignment]
    gain_to_target = None  # type: ignore[assignment]


class FakeStore:
    """Store returning in-memory audio chunks while tracking read bounds."""

    def __init__(self, audio: np.ndarray):
        # audio is (channels, frames)
        self.audio = np.asarray(audio, dtype=np.float32)
        self.reads: list[tuple[int, int]] = []

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        self.reads.append((first, count))
        channels, total_frames = self.audio.shape
        out = np.zeros((channels, count), dtype=np.float32)
        lo, hi = max(0, first), min(total_frames, first + count)
        if lo < hi:
            out[:, lo - first : hi - first] = self.audio[:, lo:hi]
        return out


def make_clip(
    media: str = "m1",
    offset: int = 0,
    length: int = 48000 * 5,
    clip_id: str = "c1",
) -> Clip:
    return Clip(
        id=clip_id,
        media=media,
        start=0,
        offset=offset,
        length=length,
    )


def test_import_exists():
    assert measure_clip is not None, "kuulas.loudness not implemented"
    assert gain_to_target is not None, "kuulas.loudness not implemented"


def test_measure_three_tones():
    rate = 48000
    duration_s = 5
    t = np.linspace(0, duration_s, duration_s * rate, endpoint=False)
    sine = np.sin(2 * np.pi * 1000 * t)

    # Calibrate unit amplitude sine against BS.1770 K-weighting at 1 kHz (~ -0.691 dB)
    # Unit sine has RMS 1/sqrt(2), power -3.01 dB,
    # K-filter gain ~ +0.691 dB => ~ -3.01 LUFS
    for target_lufs in (-30.0, -20.0, -12.0):
        # Amplitude A gives level -3.01 + 20*log10(A)
        # So 20*log10(A) = target_lufs - (-3.01) => A = 10^((target_lufs + 3.01) / 20)
        amp = 10 ** ((target_lufs + 3.01) / 20)
        tone_mono = (amp * sine)[None, :].astype(np.float32)

        store = FakeStore(tone_mono)
        clip = make_clip(length=duration_s * rate)
        measured = measure_clip(store, clip, rate)

        assert measured is not None
        assert abs(measured - target_lufs) <= 0.3


def test_silent_clip_gives_none():
    rate = 48000
    duration_s = 3
    silence = np.zeros((1, duration_s * rate), dtype=np.float32)
    store = FakeStore(silence)
    clip = make_clip(length=duration_s * rate)

    assert measure_clip(store, clip, rate) is None


def test_very_short_clip_gives_none():
    rate = 48000
    # 50 ms is shorter than the BS.1770 400 ms gating block minimum
    short_tone = np.zeros((1, int(0.05 * rate)), dtype=np.float32)
    store = FakeStore(short_tone)
    clip = make_clip(length=short_tone.shape[1])

    assert measure_clip(store, clip, rate) is None


def test_reads_in_chunks_of_at_most_60_seconds():
    rate = 48000
    duration_s = 180  # 3 minutes
    amp = 10 ** ((-20.0 + 3.01) / 20)
    t = np.linspace(0, duration_s, duration_s * rate, endpoint=False)
    tone = (amp * np.sin(2 * np.pi * 1000 * t))[None, :].astype(np.float32)

    store = FakeStore(tone)
    clip = make_clip(length=duration_s * rate)

    measured = measure_clip(store, clip, rate)
    assert measured is not None
    assert abs(measured - -20.0) <= 0.3

    # Assert store was read in chunks of at most 60 s
    assert len(store.reads) >= 3
    max_chunk = max(count for _, count in store.reads)
    assert max_chunk <= 60 * rate


def test_offset_and_length_select_correct_range():
    rate = 48000
    amp = 10 ** ((-20.0 + 3.01) / 20)
    t = np.linspace(0, 5, 5 * rate, endpoint=False)
    tone_5s = (amp * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)

    # 2s silence, 5s tone, 2s silence
    full_audio = np.concatenate([
        np.zeros(2 * rate, dtype=np.float32),
        tone_5s,
        np.zeros(2 * rate, dtype=np.float32),
    ])[None, :]

    store = FakeStore(full_audio)
    clip = make_clip(offset=2 * rate, length=5 * rate)

    measured = measure_clip(store, clip, rate)
    assert measured is not None
    assert abs(measured - -20.0) <= 0.3

    # Ensure all reads fall strictly within the clip range [2*rate, 7*rate]
    for first, count in store.reads:
        assert first >= 2 * rate
        assert first + count <= 7 * rate


def test_mono_equals_same_signal_as_stereo_within_point_three_lu():
    rate = 48000
    duration_s = 5
    amp = 10 ** ((-20.0 + 3.01) / 20)
    t = np.linspace(0, duration_s, duration_s * rate, endpoint=False)
    mono_tone = (amp * np.sin(2 * np.pi * 1000 * t))[None, :].astype(np.float32)

    # Constant-power center panning: each channel scaled by 1/sqrt(2)
    stereo_tone = np.vstack([
        mono_tone[0] / np.sqrt(2),
        mono_tone[0] / np.sqrt(2),
    ]).astype(np.float32)

    store_mono = FakeStore(mono_tone)
    store_stereo = FakeStore(stereo_tone)

    clip = make_clip(length=duration_s * rate)

    loud_mono = measure_clip(store_mono, clip, rate)
    loud_stereo = measure_clip(store_stereo, clip, rate)

    assert loud_mono is not None
    assert loud_stereo is not None
    assert abs(loud_mono - loud_stereo) <= 0.3


def test_gain_to_target():
    # None handling
    assert gain_to_target(None, -16.0) is None
    assert gain_to_target(-20.0, None) is None
    assert gain_to_target(None, None) is None

    # Normal cases
    # Quieter by 4 LUFS -> need +4 dB
    assert gain_to_target(-20.0, -16.0) == pytest.approx(4.0)
    # Louder by 4 LUFS -> need -4 dB
    assert gain_to_target(-12.0, -16.0) == pytest.approx(-4.0)

    # Caps defined by ops.CLIP_GAIN_RANGE (-60.0, 12.0)
    low, high = CLIP_GAIN_RANGE
    # 20 dB boost requested -> capped at 12.0
    assert gain_to_target(-36.0, -16.0) == pytest.approx(high)
    # 70 dB attenuation requested -> capped at -60.0
    assert gain_to_target(50.0, -16.0) == pytest.approx(low)
