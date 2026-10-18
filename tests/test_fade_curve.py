"""Fade curve gains: fade_gain, fade_out_gain, fade_table.

Pure Python, stdlib only, no imports from kuulas. Errors are plain
ValueError; there is no user-facing text.
"""

import math

import pytest

from kuulas.fade_curve import fade_gain, fade_out_gain, fade_table

SHAPES = ("linear", "equal_power", "cosine", "exponential")


def test_fade_in_starts_at_zero_and_ends_at_one():
    for shape in SHAPES:
        assert fade_gain(0, 100, shape) == 0.0
        assert fade_gain(100, 100, shape) == 1.0


def test_fade_gain_linear():
    assert fade_gain(0, 100, "linear") == 0.0
    assert fade_gain(25, 100, "linear") == pytest.approx(0.25)
    assert fade_gain(50, 100, "linear") == pytest.approx(0.5)
    assert fade_gain(75, 100, "linear") == pytest.approx(0.75)
    assert fade_gain(100, 100, "linear") == 1.0


def test_fade_gain_equal_power():
    assert fade_gain(0, 100, "equal_power") == 0.0
    assert fade_gain(50, 100, "equal_power") == pytest.approx(math.sin(math.pi / 4))
    assert fade_gain(100, 100, "equal_power") == 1.0


def test_fade_gain_cosine():
    assert fade_gain(0, 100, "cosine") == 0.0
    assert fade_gain(50, 100, "cosine") == pytest.approx(0.5)
    assert fade_gain(100, 100, "cosine") == 1.0


def test_fade_gain_exponential():
    assert fade_gain(0, 100, "exponential") == 0.0
    assert fade_gain(50, 100, "exponential") == pytest.approx(0.25)
    assert fade_gain(100, 100, "exponential") == 1.0


def test_fade_gain_position_is_clamped():
    for shape in SHAPES:
        assert fade_gain(-10, 100, shape) == fade_gain(0, 100, shape) == 0.0
        assert fade_gain(150, 100, shape) == fade_gain(100, 100, shape) == 1.0


def test_fade_out_gain_is_mirrored():
    for shape in SHAPES:
        assert fade_out_gain(0, 100, shape) == fade_gain(100, 100, shape) == 1.0
        assert fade_out_gain(100, 100, shape) == fade_gain(0, 100, shape) == 0.0
        assert fade_out_gain(25, 100, shape) == fade_gain(75, 100, shape)


def test_fade_table_spans_zero_to_one():
    for shape in SHAPES:
        table = fade_table(100, shape, 5)
        assert len(table) == 5
        assert table[0] == 0.0
        assert table[-1] == 1.0


def test_fade_table_linear_points_are_evenly_spaced():
    table = fade_table(100, "linear", 5)
    assert table == [0.0, pytest.approx(0.25), pytest.approx(0.5),
                     pytest.approx(0.75), 1.0]


def test_fade_table_points_count_matches():
    assert len(fade_table(100, "linear", 2)) == 2
    assert len(fade_table(100, "linear", 11)) == 11


def test_fade_table_points_below_two_raise_value_error():
    with pytest.raises(ValueError, match="points"):
        fade_table(100, "linear", 1)
    with pytest.raises(ValueError, match="points"):
        fade_table(100, "linear", 0)


def test_fade_gain_unknown_shape_raises_value_error():
    with pytest.raises(ValueError, match="shape"):
        fade_gain(50, 100, "unknown")


def test_fade_gain_non_positive_length_raises_value_error():
    for shape in SHAPES:
        with pytest.raises(ValueError, match="length"):
            fade_gain(10, 0, shape)
        with pytest.raises(ValueError, match="length"):
            fade_gain(10, -5, shape)
