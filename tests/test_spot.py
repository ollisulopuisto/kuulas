"""Tests for typed time parsing and spot delta calculation."""

from __future__ import annotations

import pytest

from kuulas.messages import KuulasError, set_language
from kuulas.spot import Spot, parse_spot, spot_delta

RATE = 48_000


class TestParseSpot:
    def test_hours_minutes_seconds_dot_milliseconds(self):
        spot = parse_spot("1:02:03.500", RATE)
        assert spot == Spot("absolute", round(3723.5 * RATE))

    def test_hours_minutes_seconds_comma_milliseconds(self):
        spot = parse_spot("1:02:03,500", RATE)
        assert spot == Spot("absolute", round(3723.5 * RATE))

    def test_minutes_seconds(self):
        spot = parse_spot("2:03", RATE)
        assert spot == Spot("absolute", 123 * RATE)

    def test_seconds_decimal(self):
        spot = parse_spot("62.5", RATE)
        assert spot == Spot("absolute", round(62.5 * RATE))

    def test_relative_milliseconds_positive(self):
        spot = parse_spot("+120", RATE)
        assert spot == Spot("relative", round(0.12 * RATE))

    def test_relative_milliseconds_negative(self):
        spot = parse_spot("-120", RATE)
        assert spot == Spot("relative", -round(0.12 * RATE))

    def test_relative_seconds_positive(self):
        spot = parse_spot("+1.5s", RATE)
        assert spot == Spot("relative", round(1.5 * RATE))

    def test_relative_seconds_negative(self):
        spot = parse_spot("-0.5s", RATE)
        assert spot == Spot("relative", -round(0.5 * RATE))

    def test_surrounding_spaces_are_ignored(self):
        spot = parse_spot("  2:03  ", RATE)
        assert spot == Spot("absolute", 123 * RATE)

    def test_rounds_to_nearest_frame(self):
        spot = parse_spot("0.00002", RATE)
        assert spot == Spot("absolute", 1)

    def test_rejects_empty_string(self):
        with pytest.raises(KuulasError):
            parse_spot("", RATE)

    def test_rejects_gibberish(self):
        with pytest.raises(KuulasError):
            parse_spot("abc", RATE)

    def test_rejects_too_many_colons(self):
        with pytest.raises(KuulasError):
            parse_spot("1:2:3:4", RATE)

    def test_rejects_seconds_over_60(self):
        with pytest.raises(KuulasError):
            parse_spot("1:75", RATE)

    def test_rejects_negative_absolute(self):
        with pytest.raises(KuulasError):
            parse_spot("-2:03", RATE)

    def test_error_message_is_translated(self):
        set_language("fi")
        with pytest.raises(KuulasError) as exc_info:
            parse_spot("abc", RATE)
        text = str(exc_info.value)
        assert "abc" in text
        assert text != "error.spot.invalid"


class TestSpotDelta:
    def test_absolute_moves_current_frame_to_spot(self):
        spot = Spot("absolute", 1000)
        assert spot_delta(spot, current_frame=400, playhead_frame=500) == 600

    def test_relative_applies_offset(self):
        spot = Spot("relative", 250)
        assert spot_delta(spot, current_frame=400, playhead_frame=500) == 250

    def test_relative_negative_offset(self):
        spot = Spot("relative", -250)
        assert spot_delta(spot, current_frame=400, playhead_frame=500) == -250
