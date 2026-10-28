from kuulas_recorder.sources import counter_frame


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
