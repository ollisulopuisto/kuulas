"""Converting timeline frame positions when the sample rate changes (WP27)."""

import random
from itertools import pairwise

import pytest

from kuulas.rate_convert import (
    MONO_SUM_DB,
    convert_chain,
    convert_frame,
    convert_span,
    master_gain_db_for_mono,
)


def test_convert_44100_to_48000_and_back_is_within_one_frame():
    frame = 123_456
    at_48k = convert_frame(frame, 44_100, 48_000)
    back = convert_frame(at_48k, 48_000, 44_100)
    assert abs(back - frame) <= 1


def test_adjacent_spans_stay_adjacent_over_1000_random_chained_spans():
    rng = random.Random(20261018)  # noqa: S311  # deterministic test data, not cryptography
    old_rate, new_rate = 44_100, 48_000
    spans = []
    start = 0
    for _ in range(1000):
        length = rng.randint(1, 1000)
        spans.append((start, length))
        start += length  # next span touches this one's end

    converted = convert_chain(spans, old_rate, new_rate)
    assert len(converted) == len(spans)
    for (start0, length0), (new_start, new_length) in zip(spans, converted, strict=True):
        assert new_start == convert_frame(start0, old_rate, new_rate)
        assert new_length == (
            convert_frame(start0 + length0, old_rate, new_rate) - new_start
        )
    for previous, following in pairwise(converted):
        # clips that touched still touch: converted starts never go backwards
        assert following[0] >= previous[0] + previous[1]


def test_span_of_length_zero_converts_to_empty_span():
    assert convert_span(44_100, 0, 44_100, 48_000) == (48_000, 0)


def test_negative_frame_raises_value_error():
    with pytest.raises(ValueError, match="negative"):
        convert_frame(-1, 44_100, 48_000)
    with pytest.raises(ValueError, match="negative"):
        convert_frame(-5, 48_000, 44_100)


def test_non_positive_rate_raises_value_error():
    with pytest.raises(ValueError, match="sample rates"):
        convert_frame(10, 0, 48_000)
    with pytest.raises(ValueError, match="sample rates"):
        convert_frame(10, 44_100, -44_100)
    with pytest.raises(ValueError, match="sample rates"):
        convert_span(0, 5, 44_100, 0)


def test_half_up_rounding_on_x5_case():
    # exactly 0.5 rounds up, not to even
    assert convert_frame(1, 2, 1) == 1
    assert convert_frame(3, 2, 1) == 2
    assert convert_frame(1, 4, 2) == 1


def test_same_rate_returns_the_input():
    assert convert_frame(98_765, 48_000, 48_000) == 98_765
    assert convert_span(10, 20, 48_000, 48_000) == (10, 20)
    assert convert_chain([(0, 5), (7, 3)], 48_000, 48_000) == [(0, 5), (7, 3)]


def test_spans_separated_by_one_frame_never_overlap_at_48000_to_44100():
    # original gap: 11 - 10 = 1 frame
    converted = convert_chain([(0, 10), (11, 5)], 48_000, 44_100)
    assert converted[0][0] + converted[0][1] <= converted[1][0]
    assert converted[1][0] - (converted[0][0] + converted[0][1]) >= 0


def test_master_gain_db_for_mono_is_minus_three():
    assert master_gain_db_for_mono() == -3.0
    assert MONO_SUM_DB == -3.0
