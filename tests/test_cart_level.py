"""Cart arithmetic needs neither a device nor audio files."""

import pytest

from kuulas.cart_level import cart_gain_db, trimmed_length


@pytest.mark.parametrize(("stop", "expected"), [(300, 200), (180, 80), (400, 200),
                                               (100, 1), (50, 1)])
def test_trim_never_extends_and_keeps_one_frame(stop, expected):
    assert trimmed_length(100, 200, stop) == expected


@pytest.mark.parametrize(("voice", "entry", "peak", "trim", "expected"), [
    (-23, -33, -20, 0, 10), (-23, -13, -2, 0, -10),
    (-23, -43, -5, 0, 4), (-23, -33, -20, 2, 12),
    (None, -33, -20, 0, 10),
])
def test_gain_matches_voice_or_reference_without_clipping(
        voice, entry, peak, trim, expected):
    assert cart_gain_db(voice, entry, peak, trim, reference=-23) == expected
