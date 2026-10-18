"""Tests for nudge step calculations."""

from __future__ import annotations

import pytest

from kuulas.messages import KuulasError, set_language
from kuulas.nudge_steps import LEVELS, level_for, next_level, nudge_frames


class TestNudgeFrames:
    @pytest.mark.parametrize("rate", [44_100, 48_000])
    def test_fine_is_one_millisecond(self, rate):
        assert nudge_frames(rate, "fine") == max(1, round(rate * 0.001))

    @pytest.mark.parametrize("rate", [44_100, 48_000])
    def test_normal_is_ten_milliseconds(self, rate):
        assert nudge_frames(rate, "normal") == max(1, round(rate * 0.01))

    @pytest.mark.parametrize("rate", [44_100, 48_000])
    def test_coarse_is_one_hundred_milliseconds(self, rate):
        assert nudge_frames(rate, "coarse") == max(1, round(rate * 0.1))

    @pytest.mark.parametrize("rate", [44_100, 48_000])
    def test_second_is_one_second(self, rate):
        assert nudge_frames(rate, "second") == max(1, round(rate * 1.0))

    def test_rate_of_one_rounds_to_one_frame(self):
        assert nudge_frames(1, "fine") == 1

    def test_zero_rate_rounds_up_to_one_frame(self):
        assert nudge_frames(0, "fine") == 1


class TestLevelFor:
    def test_no_modifier_is_normal(self):
        assert level_for(shift=False, alt=False) == "normal"

    def test_shift_is_coarse(self):
        assert level_for(shift=True, alt=False) == "coarse"

    def test_alt_is_fine(self):
        assert level_for(shift=False, alt=True) == "fine"

    def test_shift_alt_is_second(self):
        assert level_for(shift=True, alt=True) == "second"


class TestNextLevel:
    def test_climbs_up(self):
        assert next_level("fine", "up") == "normal"
        assert next_level("normal", "up") == "coarse"
        assert next_level("coarse", "up") == "second"

    def test_top_stays(self):
        assert next_level("second", "up") == "second"

    def test_steps_down(self):
        assert next_level("second", "down") == "coarse"
        assert next_level("coarse", "down") == "normal"
        assert next_level("normal", "down") == "fine"

    def test_bottom_stays(self):
        assert next_level("fine", "down") == "fine"

    def test_unknown_level_raises(self):
        with pytest.raises(KuulasError):
            next_level("huge", "up")

    def test_error_is_translated_finnish(self):
        set_language("fi")
        with pytest.raises(KuulasError) as exc_info:
            next_level("huge", "up")
        text = str(exc_info.value)
        assert "huge" in text
        assert text != "error.nudge_steps.unknown_level"


class TestLevelsSequence:
    def test_levels_are_in_order(self):
        assert LEVELS == ("fine", "normal", "coarse", "second")
