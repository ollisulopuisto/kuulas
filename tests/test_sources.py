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


def test_counter_block_exact_float32_values():
    """Verify exact float32 signal values at min, zero, and max 24-bit PCM bounds."""
    # Frame 0 on channel 0 -> (0 % 2**20) - 2**19 = -2**19 = -524288
    # Exact float32: -524288 / 8388608.0 = -0.0625
    block_min = counter_block(first=0, frames=1, channels=1)
    assert block_min[0, 0] == np.float32(-524288 / (1 << 23))
    assert block_min[0, 0] == np.float32(-0.0625)

    # Frame 2**19 on channel 0 -> (2**19 % 2**20) - 2**19 = 0
    # Exact float32: 0.0
    block_zero = counter_block(first=1 << 19, frames=1, channels=1)
    assert block_zero[0, 0] == np.float32(0.0)

    # Frame 2**20 - 1 on channel 0 -> (2**20 - 1) - 2**19 = 2**19 - 1 = 524287
    # Exact float32: 524287 / 8388608.0
    block_max = counter_block(first=(1 << 20) - 1, frames=1, channels=1)
    assert block_max[0, 0] == np.float32(524287 / (1 << 23))

    # Verify float32 precision is exact across a sample block of 1000 frames
    block = counter_block(first=0, frames=1000, channels=3)
    ints_expected = (
        (np.arange(1000)[:, None] + 1000 * np.arange(3)[None, :]) % (1 << 20)
        - (1 << 19)
    )
    ints_recovered = np.round(block.astype(np.float64) * (1 << 23)).astype(np.int64)
    np.testing.assert_array_equal(ints_recovered, ints_expected)


def test_counter_block_multichannel_offsets():
    """Verify that each channel c has an explicit frame offset of 1000 * c."""
    frames = 50
    channels = 4
    first = 1234
    block = counter_block(first, frames, channels)

    for c in range(channels):
        # Channel c at frame n should equal channel 0 at frame n + 1000 * c
        block_ch0_shifted = counter_block(first + 1000 * c, frames, 1)
        np.testing.assert_array_equal(block[:, c : c + 1], block_ch0_shifted)


def test_counter_block_large_and_negative_frames():
    """Verify counter_block with negative and large frame start numbers."""
    # Negative frame index
    first_neg = -50
    frames = 100
    channels = 2
    block_neg = counter_block(first_neg, frames, channels)
    assert block_neg.shape == (frames, channels)
    assert block_neg.dtype == np.float32

    for c in range(channels):
        for i in range(frames):
            frame_num = first_neg + i
            val = round(float(block_neg[i, c]) * (1 << 23))
            assert counter_frame(val, channel=c) == frame_num % (1 << 20)

    # Large frame index > 2**20
    first_large = (1 << 20) * 5 + 12345
    block_large = counter_block(first_large, frames, channels)
    for c in range(channels):
        for i in range(frames):
            frame_num = first_large + i
            val = round(float(block_large[i, c]) * (1 << 23))
            assert counter_frame(val, channel=c) == frame_num % (1 << 20)


def test_counter_block_zero_channels_or_frames():
    """Verify edge cases with 0 channels or 0 frames."""
    block_zero_ch = counter_block(first=10, frames=20, channels=0)
    assert block_zero_ch.shape == (20, 0)
    assert block_zero_ch.dtype == np.float32

    block_zero_fr = counter_block(first=10, frames=0, channels=4)
    assert block_zero_fr.shape == (0, 4)
    assert block_zero_fr.dtype == np.float32


def test_counter_block_counter_frame_roundtrip():
    """Verify full roundtrip conversion between counter_block and counter_frame."""
    first = 98765
    frames = 200
    channels = 3
    block = counter_block(first, frames, channels)

    for c in range(channels):
        for i in range(frames):
            float_val = float(block[i, c])
            int_val = round(float_val * (1 << 23))
            recovered_n = counter_frame(int_val, channel=c)
            expected_n = (first + i) % (1 << 20)
            assert recovered_n == expected_n
