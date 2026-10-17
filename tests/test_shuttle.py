"""Tests for JKL shuttle key logic."""

from __future__ import annotations

import pytest

from kuulas.messages import KuulasError, set_language
from kuulas.shuttle import LADDER, held_scrub_speed, press, scrub_style


class TestPressL:
    def test_from_stop_goes_to_first_step(self):
        assert press(0.0, "l") == 1.0

    def test_climbs_ladder(self):
        assert press(1.0, "l") == 1.5
        assert press(1.5, "l") == 2.0
        assert press(2.0, "l") == 3.0
        assert press(3.0, "l") == 5.0

    def test_stays_at_top(self):
        assert press(5.0, "l") == 5.0
        assert press(5.0, "l") == 5.0

    def test_from_negative_restarts(self):
        assert press(-3.0, "l") == 1.0


class TestPressJ:
    def test_from_stop_goes_to_negative_first_step(self):
        assert press(0.0, "j") == -1.0

    def test_climbs_negative_ladder(self):
        assert press(-1.0, "j") == -1.5
        assert press(-1.5, "j") == -2.0
        assert press(-2.0, "j") == -3.0
        assert press(-3.0, "j") == -5.0

    def test_stays_at_bottom(self):
        assert press(-5.0, "j") == -5.0
        assert press(-5.0, "j") == -5.0

    def test_from_positive_restarts(self):
        assert press(3.0, "j") == -1.0


class TestPressK:
    def test_stops_from_positive(self):
        assert press(5.0, "k") == 0.0

    def test_stops_from_negative(self):
        assert press(-5.0, "k") == 0.0

    def test_stops_from_stop(self):
        assert press(0.0, "k") == 0.0


class TestPressUnknownKey:
    def test_unknown_key_raises(self):
        with pytest.raises(KuulasError):
            press(0.0, "x")

    def test_error_is_translated_to_finnish(self):
        set_language("fi")
        with pytest.raises(KuulasError) as exc_info:
            press(0.0, "x")
        text = str(exc_info.value)
        assert text != "error.shuttle.unknown_key"


class TestScrubStyle:
    def test_tape_at_low_speeds(self):
        assert scrub_style(0.0) == "tape"
        assert scrub_style(1.0) == "tape"
        assert scrub_style(-1.0) == "tape"
        assert scrub_style(2.0) == "tape"
        assert scrub_style(-2.0) == "tape"

    def test_grains_at_high_speeds(self):
        assert scrub_style(3.0) == "grains"
        assert scrub_style(-3.0) == "grains"
        assert scrub_style(5.0) == "grains"
        assert scrub_style(-5.0) == "grains"


class TestHeldScrubSpeed:
    def test_l_gives_positive_slow_speed(self):
        assert held_scrub_speed("l") == 0.25

    def test_j_gives_negative_slow_speed(self):
        assert held_scrub_speed("j") == -0.25

    def test_unknown_direction_raises(self):
        with pytest.raises(KuulasError):
            held_scrub_speed("x")


@pytest.mark.parametrize(("start", "key"), [
    (0.0, "l"), (1.0, "l"), (1.5, "l"), (2.0, "l"), (3.0, "l"), (5.0, "l"),
    (0.0, "j"), (-1.0, "j"), (-1.5, "j"), (-2.0, "j"), (-3.0, "j"), (-5.0, "j"),
    (5.0, "k"), (-5.0, "k"), (0.0, "k"),
])
def test_press_returns_only_ladder_values_or_zero(start, key):
    result = press(start, key)
    assert result == 0.0 or abs(result) in LADDER
