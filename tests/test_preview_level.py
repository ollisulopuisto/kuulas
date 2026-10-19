"""The clipboard preview level (WP82): gain from loudness, and the safety limiter."""

import numpy as np
import pytest

from kuulas import preview_level as pl


def test_reference_is_the_average_of_the_speech_levels_in_the_power_domain():
    assert pl.reference_lufs([-20.0, -20.0], None) == pytest.approx(-20.0)
    assert -25.0 < pl.reference_lufs([-30.0, -20.0], None) < -20.0  # nearer the louder


def test_reference_ignores_tracks_without_a_level():
    assert pl.reference_lufs([None, -21.0], None) == pytest.approx(-21.0)


def test_without_analysis_the_reference_comes_from_the_peak():
    assert pl.reference_lufs([], -6.0) == pytest.approx(-6.0 - pl.PEAK_TO_LUFS_DB)


def test_an_empty_or_silent_project_gets_the_conservative_default():
    assert pl.reference_lufs([], None) == pl.DEFAULT_REFERENCE_LUFS == -23.0
    assert pl.reference_lufs([None], None) == -23.0


def test_a_louder_entry_is_turned_down_to_the_reference():
    assert pl.preview_gain_db(-23.0, -14.0) == pytest.approx(-9.0)


def test_a_quieter_entry_is_never_boosted():
    assert pl.preview_gain_db(-23.0, -30.0) == 0.0
    assert pl.preview_gain_db(-23.0, -23.0) == 0.0


def test_an_unmeasurable_entry_is_left_alone():
    assert pl.preview_gain_db(-23.0, None) == 0.0


def test_the_peak_guard_keeps_the_entry_under_the_project_peak():
    # Loudness says 0 dB, but the entry peaks at -1 and the project at -10.
    assert pl.preview_gain_db(-23.0, -23.0, entry_peak_db=-1.0,
                              project_peak_db=-10.0) == pytest.approx(-9.0)


def test_the_peak_guard_never_boosts_either():
    got = pl.preview_gain_db(-23.0, -40.0, entry_peak_db=-30.0, project_peak_db=-3.0)
    assert got == 0.0


def test_limiter_leaves_quiet_audio_untouched():
    x = np.array([[0.1, -0.2, 0.3], [0.0, 0.25, -0.3]], dtype=np.float32).T
    assert np.array_equal(pl.soft_limit(x), x)


def test_limiter_never_exceeds_the_ceiling():
    x = np.linspace(-8.0, 8.0, 1001, dtype=np.float32).reshape(-1, 1).repeat(2, axis=1)
    ceiling = 10 ** (pl.CEILING_DB / 20)
    assert np.abs(pl.soft_limit(x)).max() <= ceiling + 1e-6


def test_limiter_is_monotonic_odd_and_does_not_change_its_input():
    x = np.linspace(-3.0, 3.0, 601, dtype=np.float32).reshape(-1, 1).repeat(2, axis=1)
    before = x.copy()
    y = pl.soft_limit(x)
    assert np.array_equal(x, before)
    assert (np.diff(y[:, 0]) >= 0).all()
    assert np.allclose(y[::-1], -y, atol=1e-6)
    assert y.dtype == np.float32
