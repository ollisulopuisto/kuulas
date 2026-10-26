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
