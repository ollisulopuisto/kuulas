import pytest

from kuulas_recorder.sources import SourceError, check_rate


def test_check_rate_matching():
    # Exact match
    check_rate("Device A", 48000.0, 48000)
    check_rate("Device B", 44100.0, 44100)

    # Float values that round to the exact match
    check_rate("Device C", 48000.1, 48000)
    check_rate("Device D", 47999.9, 48000)


def test_check_rate_mismatch():
    with pytest.raises(SourceError) as exc_info:
        check_rate("Device A", 44100.0, 48000)

    assert exc_info.value.key == "device_rate_mismatch"
    assert "Device A runs at 44100 Hz, not 48000 Hz." in str(exc_info.value)
    assert "Set it to 48000 Hz" in str(exc_info.value)

    with pytest.raises(SourceError) as exc_info:
        check_rate("Device B", 48000.0, 44100)

    assert exc_info.value.key == "device_rate_mismatch"
    assert "Device B runs at 48000 Hz, not 44100 Hz." in str(exc_info.value)
    assert "Set it to 44100 Hz" in str(exc_info.value)
