import pytest

from kuulas_recorder.sources import SourceError, check_rate, resolve_device


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


def test_resolve_device_by_name_and_index_exact_match():
    devices = [
        {"index": 0, "name": "Built-in Mic", "default": True},
        {"index": 1, "name": "USB Mic", "default": False},
    ]
    matched = resolve_device(devices, {"index": 1, "name": "USB Mic"})
    assert matched == {"index": 1, "name": "USB Mic", "default": False}


def test_resolve_device_by_name_and_index_fallback_name_wins():
    devices = [
        {"index": 0, "name": "Built-in Mic", "default": True},
        {"index": 2, "name": "USB Mic", "default": False},
    ]
    # Device USB Mic changed index from 1 to 2; name match fallback should find it
    matched = resolve_device(devices, {"index": 1, "name": "USB Mic"})
    assert matched == {"index": 2, "name": "USB Mic", "default": False}


def test_resolve_device_by_name_only():
    devices = [
        {"index": 0, "name": "Built-in Mic", "default": True},
        {"index": 1, "name": "USB Mic", "default": False},
    ]
    assert resolve_device(devices, "USB Mic") == devices[1]
    assert resolve_device(devices, {"name": "USB Mic"}) == devices[1]


def test_resolve_device_by_index_only():
    devices = [
        {"index": 0, "name": "Built-in Mic", "default": True},
        {"index": 1, "name": "USB Mic", "default": False},
    ]
    assert resolve_device(devices, 1) == devices[1]
    assert resolve_device(devices, {"index": 1}) == devices[1]


def test_resolve_device_default():
    devices = [
        {"index": 0, "name": "Built-in Mic", "default": True},
        {"index": 1, "name": "USB Mic", "default": False},
    ]
    assert resolve_device(devices, None) == devices[0]
    assert resolve_device(devices, True) == devices[0]
    assert resolve_device(devices, False) == devices[0]
    assert resolve_device(devices, {}) == devices[0]


def test_resolve_device_duplicate_names():
    devices = [
        {"index": 0, "name": "USB Mic", "default": False},
        {"index": 1, "name": "USB Mic", "default": True},
    ]
    # Exact match by name + index specifies index 1
    assert resolve_device(devices, {"name": "USB Mic", "index": 1}) == devices[1]
    # Out-of-date index fallback picks first matching name
    assert resolve_device(devices, {"name": "USB Mic", "index": 99}) == devices[0]
    # Name-only query picks first matching name
    assert resolve_device(devices, "USB Mic") == devices[0]


def test_resolve_device_not_found_errors():
    devices = [{"index": 0, "name": "Built-in Mic", "default": True}]

    # Unknown device name
    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, "Nonexistent Mic")
    assert exc_info.value.key == "device_not_found"
    assert "No input device named 'Nonexistent Mic'." in str(exc_info.value)

    # Unknown device name in dict
    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, {"name": "Nonexistent Mic", "index": 0})
    assert exc_info.value.key == "device_not_found"
    assert "No input device named 'Nonexistent Mic'." in str(exc_info.value)

    # Unknown device index
    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, 5)
    assert exc_info.value.key == "device_not_found"
    assert "No input device number 5." in str(exc_info.value)

    # Unknown device index in dict
    with pytest.raises(SourceError) as exc_info:
        resolve_device(devices, {"index": 5})
    assert exc_info.value.key == "device_not_found"
    assert "No input device number 5." in str(exc_info.value)

    # No default device present
    no_default_devices = [{"index": 0, "name": "Built-in Mic", "default": False}]
    with pytest.raises(SourceError) as exc_info:
        resolve_device(no_default_devices, None)
    assert exc_info.value.key == "device_not_found"
    assert "There is no default input device." in str(exc_info.value)

    # Empty devices list
    with pytest.raises(SourceError) as exc_info:
        resolve_device([], None)
    assert exc_info.value.key == "device_not_found"
    assert "There is no default input device." in str(exc_info.value)
