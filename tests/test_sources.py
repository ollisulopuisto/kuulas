import numpy as np
import pytest

from kuulas_recorder.sources import (
    SourceError,
    counter_block,
    counter_frame,
    resolve_device,
)


def test_resolve_device_by_name_and_index_exact_match():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert resolve_device(devices, {"index": 1, "name": "B"}) == {"index": 1, "name": "B"}


def test_resolve_device_by_name_and_index_name_wins():
    devices = [{"index": 0, "name": "A"}, {"index": 2, "name": "B"}]
    # Device B changed index from 1 to 2, name match should still find it.
    assert resolve_device(devices, {"index": 1, "name": "B"}) == {"index": 2, "name": "B"}


def test_resolve_device_by_name_only():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert resolve_device(devices, "B") == {"index": 1, "name": "B"}
    assert resolve_device(devices, {"name": "B"}) == {"index": 1, "name": "B"}


def test_resolve_device_by_index_only():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B"}]
    assert resolve_device(devices, 1) == {"index": 1, "name": "B"}
    assert resolve_device(devices, {"index": 1}) == {"index": 1, "name": "B"}


def test_resolve_device_default():
    devices = [{"index": 0, "name": "A"}, {"index": 1, "name": "B", "default": True}]
    assert resolve_device(devices, None) == {"index": 1, "name": "B", "default": True}
    assert resolve_device(devices, True) == {"index": 1, "name": "B", "default": True}
    assert resolve_device(devices, False) == {"index": 1, "name": "B", "default": True}
    assert resolve_device(devices, {}) == {"index": 1, "name": "B", "default": True}


def test_resolve_device_not_found_errors():
    devices = [{"index": 0, "name": "A"}]

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, "B")
    assert exc_info.value.key == "device_not_found"
    assert "B" in exc_info.value.text

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, {"name": "B", "index": 0})
    assert exc_info.value.key == "device_not_found"

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, 1)
    assert exc_info.value.key == "device_not_found"
    assert "1" in exc_info.value.text

    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, None)
    assert exc_info.value.key == "device_not_found"
    assert "default" in exc_info.value.text


def test_counter_block_shape_and_type():
    """Verify counter_block produces the expected shape and dtype."""
    block = counter_block(first=10, frames=100, channels=2)
    assert block.shape == (100, 2)
    assert block.dtype == np.float32

    # Check zero frames
    empty_block = counter_block(first=0, frames=0, channels=2)
    assert empty_block.shape == (0, 2)


def test_counter_block_values():
    """Verify counter_block generates the correct sequence of values."""
    first = 500
    frames = 10
    channels = 2
    block = counter_block(first, frames, channels)

    # Convert back to integers
    ints = (block * (1 << 23)).astype(np.int64)

    for c in range(channels):
        for i in range(frames):
            frame_num = first + i
            val = ints[i, c]
            # Verify counter_frame inverts correctly
            recovered_frame = counter_frame(val, channel=c)
            assert recovered_frame == frame_num % (1 << 20)


def test_counter_block_boundary():
    """Verify counter_block wraps correctly around the 2**20 boundary."""
    # Place it right at the boundary
    boundary = 1 << 20
    first = boundary - 5
    frames = 10
    channels = 1

    block = counter_block(first, frames, channels)
    ints = (block * (1 << 23)).astype(np.int64)

    for i in range(frames):
        frame_num = first + i
        val = ints[i, 0]
        recovered_frame = counter_frame(val, channel=0)

        # We expect modulo 2**20 behavior
        expected_frame = frame_num % boundary
        assert recovered_frame == expected_frame


def test_counter_frame_default_channel():
    """Verify counter_frame defaults to channel 0."""
    val = -(1 << 19)
    assert counter_frame(val) == 0
    assert counter_frame(val) == counter_frame(val, channel=0)


def test_counter_frame_known_values():
    """Verify counter_frame calculation for specific integer values on channel 0."""
    half_mod = 1 << 19
    mod = 1 << 20

    # Minimum value: -(2**19) -> frame 0
    assert counter_frame(-half_mod, channel=0) == 0

    # Value 0 -> frame 2**19
    assert counter_frame(0, channel=0) == half_mod

    # Maximum value: 2**19 - 1 -> frame 2**20 - 1
    assert counter_frame(half_mod - 1, channel=0) == mod - 1

    # Arbitrary known offset: -(2**19) + 42 -> frame 42
    assert counter_frame(-half_mod + 42, channel=0) == 42


def test_counter_frame_channels():
    """Verify counter_frame accounts for channel offsets correctly."""
    # counter_block formula: (n + 1000 * c) % 2**20 - 2**19
    # For frame n = 0 and channel c = 1: value = 1000 - 2**19
    val_ch1 = 1000 - (1 << 19)
    assert counter_frame(val_ch1, channel=1) == 0

    # For frame n = 50 and channel c = 3: value = 50 + 3000 - 2**19
    val_ch3 = 50 + 3000 - (1 << 19)
    assert counter_frame(val_ch3, channel=3) == 50


def test_counter_frame_modulo_wrapping():
    """Verify counter_frame wraps outputs to [0, 2**20 - 1]."""
    mod = 1 << 20
    # Values outside standard range should stay within [0, 2**20 - 1]
    res_large = counter_frame(mod + 10, channel=0)
    assert 0 <= res_large < mod
    assert res_large == counter_frame(10, channel=0)

    # When calculation produces negative results, Python modulo returns positive remainder
    res_neg = counter_frame(-(1 << 19) - 10, channel=0)
    assert 0 <= res_neg < mod
    assert res_neg == mod - 10
