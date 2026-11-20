"""Automatic sync measurement, synthetic audio with no shared clock."""

import numpy as np
import pytest

from kuulas.align_math import fit_drift
from kuulas.align_sound import envelope, measure
from kuulas.messages import t

RATE = 8000


def speech(seconds=80, seed=5):
    rng = np.random.default_rng(seed)
    # A smooth but aperiodic level contour, with independent fine audio texture.
    contour = rng.uniform(.02, .8, int(seconds * 20) + 1)
    levels = np.interp(np.arange(seconds * RATE) / RATE,
                       np.arange(contour.size) / 20, contour)
    return (levels * rng.standard_normal(seconds * RATE)).astype(np.float32)


def test_envelope_keeps_antiphase_stereo_and_rejects_nonfinite():
    audio = speech(2)
    stereo = np.column_stack([audio, -audio])
    assert np.allclose(envelope(stereo, RATE), envelope(audio, RATE))
    with pytest.raises(ValueError, match=t("error.sync.audio")):
        envelope(np.array([np.nan]), RATE)


def test_offset_is_measured_to_one_millisecond():
    ref = speech()
    local = ref[round(2.345 * RATE):]
    points = measure(envelope(ref, RATE), envelope(local, RATE))
    assert len(points) >= 3
    assert all(lag == pytest.approx(2.345, abs=.001) for _, lag, _ in points)


def test_short_local_can_start_far_inside_a_long_reference():
    ref = speech(180)
    local = ref[115 * RATE:145 * RATE]
    points = measure(envelope(ref, RATE), envelope(local, RATE))
    assert len(points) >= 3
    assert all(lag == pytest.approx(115, abs=.001) for _, lag, _ in points)


def test_absolute_correlation_rejects_unrelated_noise_and_silence():
    ref = speech()
    for other in (speech(seed=7), np.zeros(ref.size, dtype=np.float32)):
        assert measure(envelope(ref, RATE), envelope(other, RATE)) == []


def test_small_clock_drift_is_measured_at_both_ends():
    ref = speech(120)
    ratio = 1.0001
    local = np.interp(np.arange(int(ref.size / ratio)) * ratio,
                      np.arange(ref.size), ref)
    points = measure(envelope(ref, RATE), envelope(local, RATE))
    assert len(points) >= 6
    offset, slope = fit_drift(points)
    assert offset == pytest.approx(0, abs=.002)
    assert slope == pytest.approx(.0001, abs=.00002)


def test_a_dropped_second_is_not_smoothed_into_clock_drift():
    ref = speech(120)
    local = np.concatenate([ref[:60 * RATE], ref[round(61.2 * RATE):]])
    points = measure(envelope(ref, RATE), envelope(local, RATE))
    early = [lag for time, lag, _ in points if time < 50]
    late = [lag for time, lag, _ in points if time > 70]
    assert len(early) >= 2
    assert len(late) >= 2
    assert max(abs(lag) for lag in early) <= .001
    assert max(abs(lag - 1.2) for lag in late) <= .001


def test_twenty_minute_local_starts_at_minute_fifteen_of_hour_long_call():
    rng = np.random.default_rng(44)
    reference = rng.uniform(.05, .8, 3600 * 1000)
    local = reference[900 * 1000:2100 * 1000]
    points = measure(reference, local)
    assert len(points) >= 10
    assert all(lag == pytest.approx(900, abs=.001) for _, lag, _ in points)


def test_repetitive_audio_does_not_create_a_unique_match():
    repeated = np.tile(np.linspace(.01, .8, 1000), 60)
    assert measure(repeated, repeated) == []


def test_short_and_invalid_envelopes_cannot_make_a_plan():
    assert measure(np.zeros(1000), np.zeros(1000)) == []
    with pytest.raises(ValueError, match=t("error.sync.envelope")):
        measure(np.array([np.inf]), np.zeros(1000))
