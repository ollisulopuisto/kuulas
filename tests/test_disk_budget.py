"""Disk budget: how much recording time is left on the disk."""

import pytest

from kuulas.disk_budget import (
    bytes_per_second,
    disk_state,
    format_hm,
    seconds_left,
)


def test_bytes_per_second_is_rate_times_channels_times_sample_bytes():
    assert bytes_per_second(48000, 1, 3) == 144000
    assert bytes_per_second(44100, 2, 2) == 176400
    assert bytes_per_second(8000, 1, 1) == 8000


def test_bytes_per_second_rejects_non_positive():
    with pytest.raises(ValueError, match="rate"):
        bytes_per_second(0, 1, 3)
    with pytest.raises(ValueError, match="rate"):
        bytes_per_second(-48000, 1, 3)
    with pytest.raises(ValueError, match="channels"):
        bytes_per_second(48000, 0, 3)
    with pytest.raises(ValueError, match="bytes_per_sample"):
        bytes_per_second(48000, 1, 0)


def test_seconds_left_floors_to_whole_seconds():
    # 48000 Hz mono 24-bit = 144000 B/s, default reserve 500_000_000 B
    assert seconds_left(500_000_000 + 144000 * 100, 48000, 1, 3) == 100
    assert seconds_left(500_000_000 + 144000 * 100 + 72000, 48000, 1, 3) == 100


def test_seconds_left_is_never_negative():
    assert seconds_left(0, 48000, 1, 3) == 0
    assert seconds_left(100, 48000, 1, 3) == 0
    assert seconds_left(500_000_000, 48000, 1, 3) == 0  # reserve == free


def test_seconds_left_reserve_larger_than_free_gives_zero():
    assert seconds_left(100, 48000, 1, 3, reserve_bytes=500_000_000) == 0


def test_seconds_left_custom_reserve():
    assert seconds_left(1_000_000_000, 48000, 1, 3, reserve_bytes=100_000_000) == (
        900_000_000 // 144000
    )


def test_seconds_left_rejects_negative_free_bytes_or_reserve():
    with pytest.raises(ValueError, match="free_bytes"):
        seconds_left(-1, 48000, 1, 3)
    with pytest.raises(ValueError, match="reserve_bytes"):
        seconds_left(1000, 48000, 1, 3, reserve_bytes=-5)


def test_seconds_left_rejects_non_positive_rate_channels_bytes_per_sample():
    with pytest.raises(ValueError, match="rate"):
        seconds_left(1_000_000_000, 0, 1, 3)
    with pytest.raises(ValueError, match="channels"):
        seconds_left(1_000_000_000, 48000, 0, 3)
    with pytest.raises(ValueError, match="bytes_per_sample"):
        seconds_left(1_000_000_000, 48000, 1, 0)


def test_disk_state_boundaries():
    assert disk_state(1801) == "ok"
    assert disk_state(1800) == "warn"  # exactly warn_s
    assert disk_state(301) == "warn"
    assert disk_state(300) == "critical"  # exactly critical_s
    assert disk_state(1) == "critical"
    assert disk_state(0) == "full"


def test_disk_state_with_custom_thresholds():
    assert disk_state(601, warn_s=600, critical_s=300) == "ok"
    assert disk_state(600, warn_s=600, critical_s=300) == "warn"
    assert disk_state(300, warn_s=600, critical_s=300) == "critical"
    assert disk_state(299, warn_s=600, critical_s=300) == "critical"


def test_format_hm_below_an_hour_is_m_ss():
    assert format_hm(0) == "0:00"
    assert format_hm(47) == "0:47"
    assert format_hm(247) == "4:07"
    assert format_hm(3599) == "59:59"


def test_format_hm_at_and_above_an_hour_is_h_mm():
    assert format_hm(3600) == "1:00"
    assert format_hm(7500) == "2:05"
    assert format_hm(3661) == "1:01"


def test_format_hm_floors_seconds():
    assert format_hm(247.9) == "4:07"


def test_format_hm_rejects_negative():
    with pytest.raises(ValueError, match="seconds"):
        format_hm(-1)
