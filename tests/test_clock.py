"""The recording clock: flicks (docs/FORMAT.md, "Two clocks")."""

import pytest

from kuulas import clock
from kuulas.clock import FLICKS, flicks_to_frames, frames_to_flicks

SUPPORTED = (8000, 11025, 16000, 22050, 32000, 44100, 48000, 88200, 96000,
             176400, 192000)


@pytest.mark.parametrize("rate", SUPPORTED)
def test_flicks_are_exact_for_every_supported_rate(rate):
    clock.check_rate(rate)
    hour = 3600 * rate
    for frames in (0, 1, 2, rate - 1, rate, hour + 17, 24 * hour - 1, -rate - 3):
        flicks = frames_to_flicks(frames, rate)
        # Exact: no rounding happened on the way in...
        assert flicks * rate == frames * FLICKS
        # ...so the way back is the identity.
        assert flicks_to_frames(flicks, rate) == frames


def test_between_two_frames_rounds_half_to_even():
    per_frame = FLICKS // 48000
    assert flicks_to_frames(per_frame // 2, 48000) == 0      # 0.5 -> 0
    assert flicks_to_frames(3 * per_frame // 2, 48000) == 2  # 1.5 -> 2
    assert flicks_to_frames(per_frame // 2 + 1, 48000) == 1  # above half -> up


def test_rates_that_do_not_divide_flicks_are_refused():
    with pytest.raises(clock.RateError) as err:
        clock.check_rate(37800)
    assert err.value.key == "error.clock.rate"
    assert "37800" in str(err.value)
