"""Tests for transient onset detection and caching (WP19i)."""

from pathlib import Path

import numpy as np
import soundfile as sf

from kuulas import clock, onsets
from kuulas.media import MediaStore
from kuulas.model import Clip, Project, Track


def test_clicks_at_known_samples_in_noise_are_found_within_1ms():
    rate = 48000
    np.random.seed(42)
    n_samples = rate * 2
    # Background noise at -40 dB
    noise = (np.random.randn(n_samples) * (10 ** (-40 / 20))).astype(np.float32)

    click_samples = [24000, 72000]
    for cs in click_samples:
        noise[cs] = 0.5  # Click at -6 dB

    result_flicks = onsets.detect(noise, rate)
    assert len(result_flicks) == len(click_samples)

    result_samples = [clock.flicks_to_frames(f, rate) for f in result_flicks]
    for expected, found in zip(click_samples, result_samples, strict=True):
        diff_samples = abs(expected - found)
        diff_ms = diff_samples / rate * 1000
        assert diff_ms < 1.0


def test_steady_tone_yields_one_onset_at_its_start():
    rate = 48000
    t = np.arange(rate) / rate
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    result_flicks = onsets.detect(tone, rate)
    assert len(result_flicks) == 1

    first_sample = clock.flicks_to_frames(result_flicks[0], rate)
    # The start of the tone is at bin 0 (first ms, within 48 samples)
    assert first_sample < 48


def test_timeline_onsets_skips_muted_or_trimmed_parts():
    rate = 48000
    # Media has onsets at 0.5s, 1.0s, 1.5s, 2.0s
    media_flicks = np.array([
        clock.frames_to_flicks(int(sec * rate), rate)
        for sec in (0.5, 1.0, 1.5, 2.0)
    ], dtype=np.int64)
    onsets_by_media = {"m1": media_flicks}

    # Clip 1: plays from media 0.8s to 1.8s (frames 38400 to 86400)
    # Placed on timeline at 10000. Length is 48000 (1.0s).
    # Onsets at 1.0s (offset + 9600) and 1.5s (offset + 33600) fall inside.
    # 0.5s and 2.0s are trimmed away.
    clip1 = Clip(
        id="c1", media="m1",
        start=10000, length=48000, offset=38400,
    )
    track1 = Track(id="t1", name="Voice", clips=(clip1,))
    project = Project(rate=rate, tracks=(track1,))

    timeline = onsets.timeline_onsets(project, onsets_by_media, track_id="t1")
    # Expected timeline positions:
    # 1.0s in media is frame 48000. In clip: 10000 + (48000 - 38400) = 19600
    # 1.5s in media is frame 72000. In clip: 10000 + (72000 - 38400) = 43600
    assert timeline == [19600, 43600]

    # When clip is muted, no onsets offered
    muted_clip = Clip(
        id="c1", media="m1",
        start=10000, length=48000, offset=38400, muted=True,
    )
    t_muted_clip = Track(id="t1", name="Voice", clips=(muted_clip,))
    p_muted_clip = Project(rate=rate, tracks=(t_muted_clip,))
    assert onsets.timeline_onsets(p_muted_clip, onsets_by_media, track_id="t1") == []

    # When track is muted, no onsets offered
    t_muted_track = Track(id="t1", name="Voice", mute=True, clips=(clip1,))
    p_muted_track = Project(rate=rate, tracks=(t_muted_track,))
    assert onsets.timeline_onsets(p_muted_track, onsets_by_media, track_id="t1") == []


def test_cached_onsets_are_reused_on_reopen(tmp_path: Path):
    rate = 48000
    t = np.arange(rate) / rate
    audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav_path = tmp_path / "tone.wav"
    sf.write(str(wav_path), audio, rate)

    store = MediaStore(tmp_path / "pkg" / "media", rate=rate)
    media = store.import_file(str(wav_path))

    first_onsets = store.onsets(media.id)
    assert first_onsets is not None
    assert len(first_onsets) == 1

    # Verify cache file exists in caches/onsets/
    key = onsets.cache_key(media.sha256, rate)
    cache_file = store.cache_root / "onsets" / f"{key}.npy"
    assert cache_file.is_file()

    # Reopen store: loaded from disk cache
    reopened = MediaStore(tmp_path / "pkg" / "media", rate=rate)
    second_onsets = reopened.onsets(media.id)
    assert second_onsets is not None
    assert np.array_equal(first_onsets, second_onsets)


def test_unreadable_or_missing_media_returns_none(tmp_path: Path):
    store = MediaStore(tmp_path / "pkg" / "media", rate=48000)
    assert store.onsets("nonexistent") is None


def test_cache_key_parameters_and_algorithm():
    params = onsets.cache_params(48000)
    assert params["bin_ms"] == 1
    assert params["threshold_db"] == 12.0
    assert params["pre_ms"] == 20
    assert params["min_interval_ms"] == 50
    assert params["floor_margin_db"] == 12.0
    assert params["rate"] == 48000
    key = onsets.cache_key("a" * 64, 48000)
    assert isinstance(key, str)
    assert len(key) == 64


def test_detect_stereo_audio():
    rate = 48000
    t = np.arange(rate) / rate
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    stereo = np.stack([tone, tone], axis=0)
    result = onsets.detect(stereo, rate)
    assert len(result) == 1


def test_detect_empty_or_silence():
    assert len(onsets.detect(np.array([], dtype=np.float32), 48000)) == 0
    # Short audio under 1 ms
    assert len(onsets.detect(np.ones(10, dtype=np.float32), 48000)) == 0


def test_non_max_suppression_keeps_strongest_within_50ms():
    rate = 48000
    audio = np.zeros(rate, dtype=np.float32)
    # Click 1 at 0.500s with peak 0.4
    c1 = 24000
    audio[c1] = 0.4
    # Click 2 at 0.520s (20 ms later) with peak 0.9 (stronger)
    c2 = 24000 + int(rate * 0.020)
    audio[c2] = 0.9

    result_flicks = onsets.detect(audio, rate)
    assert len(result_flicks) == 1
    found_sample = clock.flicks_to_frames(result_flicks[0], rate)
    assert abs(found_sample - c2) < 48  # c2 was stronger and kept
