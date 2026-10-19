import pytest

from kuulas.ruler_ticks import tick_label, tick_step, tick_times


def test_step_is_the_smallest_wide_enough():
    # 100 frames per pixel at 48000: one second is 480 px wide, 0.1 s is 48 px
    assert tick_step(100, 48000, min_px=80) == 0.2
    assert tick_step(100, 48000, min_px=48) == 0.1


def test_step_falls_back_to_the_largest():
    assert tick_step(1_000_000_000, 48000) == 7200


def test_step_boundary_counts():
    assert tick_step(100, 48000, min_px=48) == 0.1


@pytest.mark.parametrize(("fpp", "rate", "px"), [(0, 48000, 80), (-1, 48000, 80),
                                                 (10, 0, 80), (10, 48000, 0)])
def test_step_bad_arguments(fpp, rate, px):
    with pytest.raises(ValueError, match="must be positive"):
        tick_step(fpp, rate, px)


def test_times_from_first_multiple():
    assert tick_times(0.3, 1.1, 0.5) == [0.5, 1.0]
    assert tick_times(0, 2, 1) == [0, 1, 2]


def test_times_no_float_drift():
    assert tick_times(0, 0.3, 0.1) == [0.0, 0.1, 0.2, 0.3]


def test_times_empty_and_errors():
    assert tick_times(5, 1, 1) == []
    with pytest.raises(ValueError, match="step"):
        tick_times(0, 1, 0)
    with pytest.raises(ValueError, match="ticks"):
        tick_times(0, 100_000, 1)


def test_labels():
    assert tick_label(65, 1) == "1:05"
    assert tick_label(3725, 1) == "1:02:05"
    assert tick_label(1.5, 0.5) == "0:01.5"
    assert tick_label(0.25, 0.05) == "0:00.25"
    assert tick_label(0, 2) == "0:00"
