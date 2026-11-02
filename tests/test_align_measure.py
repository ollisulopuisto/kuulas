"""Windowed lag measurements for align-by-sound (WP16): the pure correlator.

Each window of the candidate is slid against the reference within ±max_lag;
the measurement is (window centre in seconds, best lag in seconds, best peak
over second-best peak). ``align_math`` decides what the series means.
"""

import numpy as np
import pytest

from kuulas import align_math
from kuulas.align_measure import windowed_lags

RATE = 100  # envelopes, not audio: 100 values per second


def tone_burst(length, rng):
    """Uneven, aperiodic speech-ish envelope: periodic carriers would give the
    correlation comb teeth, and every shifted copy would look like a match."""
    smooth = np.convolve(rng.standard_normal(length), np.ones(7), mode="same")
    gate = (rng.random(length) > 0.35).astype(float)
    return smooth * gate


def test_aligned_pair_measures_zero_lag():
    rng = np.random.default_rng(7)
    ref = tone_burst(RATE * 120, rng)
    measurements = windowed_lags(ref, ref, rate=RATE, window=30, hop=15, max_lag=60)
    assert measurements
    for _time, lag, ratio in measurements:
        assert lag == pytest.approx(0.0)
        assert ratio >= 1.5


def test_shifted_pair_measures_its_offset():
    rng = np.random.default_rng(11)
    ref = tone_burst(RATE * 180, rng)
    # The candidate skips the reference's first 12.34 s: every window's content
    # sits 12.34 s later in the reference than in the candidate.
    cand = ref[1234:]
    measurements = windowed_lags(ref, cand, rate=RATE, window=30, hop=15, max_lag=60)
    lags = [lag for _t, lag, ratio in measurements if ratio >= 1.5]
    assert lags
    assert np.median(lags) == pytest.approx(12.34, abs=0.05)


def test_unrelated_audio_has_no_clear_window():
    rng = np.random.default_rng(3)
    ref = tone_burst(RATE * 120, rng)
    other = tone_burst(RATE * 120, np.random.default_rng(9))
    measurements = windowed_lags(ref, other, rate=RATE, window=30, hop=15, max_lag=60)
    clear = [m for m in measurements if m[2] >= 1.5]
    assert len(clear) <= len(measurements) // 4


def test_lag_beyond_max_lag_is_not_reported():
    rng = np.random.default_rng(5)
    ref = tone_burst(RATE * 120, rng)
    cand = ref[9000:]  # 90 s late, outside ±60 s
    measurements = windowed_lags(ref, cand, rate=RATE, window=30, hop=15, max_lag=60)
    clear = [m for m in measurements if m[2] >= 1.5]
    assert clear == []


def test_short_input_gives_no_measurements():
    short = np.zeros(10)
    assert windowed_lags(short, short, rate=RATE, window=30, hop=15, max_lag=60) == []


def test_drifting_pair_feeds_a_drift_fit():
    """A recorder 0.2 % slow: the lag grows linearly, and align_math sees the drift."""
    rng = np.random.default_rng(13)
    ref = tone_burst(RATE * 300, rng)
    # Candidate plays the same content 1.002x slower (indices stretched).
    cand = np.interp(
        np.arange(int(len(ref) * 0.98)) * 1.002, np.arange(len(ref)), ref
    )
    measurements = windowed_lags(ref, cand, rate=RATE, window=30, hop=15, max_lag=60)
    fit = align_math.fit_drift(measurements)
    assert fit is not None
    offset, slope = fit
    assert offset == pytest.approx(0.0, abs=0.2)
    assert slope == pytest.approx(0.002, rel=0.2)
    assert align_math.has_drift(slope)
