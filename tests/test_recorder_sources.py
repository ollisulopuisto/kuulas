import sys
from unittest.mock import MagicMock

import pytest

from kuulas_recorder.sources import (
    SoundDeviceSource,
    SourceError,
    ThreadedFakeSource,
    check_rate,
)


def test_check_rate_matching():
    # Exact match
    check_rate("Device A", 48000.0, 48000)
    check_rate("Device B", 44100.0, 44100)

    # Float values that round to the exact match
    check_rate("Device C", 48000.1, 48000)
    check_rate("Device D", 47999.9, 48000)


def test_check_rate_rounding_boundaries():
    # Values that round to target (48000)
    check_rate("Device B1", 47999.5, 48000)
    check_rate("Device B2", 48000.49, 48000)

    # Values that round outside target (48000)
    with pytest.raises(SourceError) as exc_info:
        check_rate("Device B3", 47999.49, 48000)
    assert exc_info.value.key == "device_rate_mismatch"
    assert "Device B3 runs at 47999 Hz, not 48000 Hz." in str(exc_info.value)

    with pytest.raises(SourceError) as exc_info:
        check_rate("Device B4", 48000.51, 48000)
    assert exc_info.value.key == "device_rate_mismatch"
    assert "Device B4 runs at 48001 Hz, not 48000 Hz." in str(exc_info.value)


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


def test_sound_device_source_rate_mismatch(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", MagicMock())
    devices = [{
        "index": 0,
        "name": "Mismatched Mic",
        "channels": 2,
        "default_rate": 44100.0,
        "hostapi": "Core Audio",
        "default": True,
    }]
    monkeypatch.setattr("kuulas_recorder.sources.input_devices", lambda: devices)

    source = SoundDeviceSource(device=0, channels=1, rate=48000, blocksize=1024)
    with pytest.raises(SourceError) as exc_info:
        source.start(on_block=lambda _b, _f, _o: None, on_lost=lambda _reason: None)

    assert exc_info.value.key == "device_rate_mismatch"
    assert "Mismatched Mic runs at 44100 Hz, not 48000 Hz." in str(exc_info.value)


def test_threaded_fake_source_rate_mismatch(monkeypatch):
    devices = [{
        "index": 0,
        "name": "Fake Mismatched Mic",
        "channels": 2,
        "default_rate": 44100.0,
        "hostapi": "fake",
        "default": True,
    }]
    monkeypatch.setattr("kuulas_recorder.sources.input_devices", lambda: devices)

    source = ThreadedFakeSource(
        want=0, channels=1, rate=48000, blocksize=1024, spec_path=""
    )
    with pytest.raises(SourceError) as exc_info:
        source.start(on_block=lambda _b, _f, _o: None, on_lost=lambda _reason: None)

    assert exc_info.value.key == "device_rate_mismatch"
    assert "Fake Mismatched Mic runs at 44100 Hz, not 48000 Hz." in str(exc_info.value)
