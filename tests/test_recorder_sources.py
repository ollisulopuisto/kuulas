import json

import pytest

from kuulas_recorder.sources import SourceError, check_rate, fake_spec


def test_check_rate_matching():
    # Exact match
    check_rate("Device A", 48000.0, 48000)
    check_rate("Device B", 44100.0, 44100)
    check_rate("Device High", 96000.0, 96000)

    # Float values that round to the exact match
    check_rate("Device C", 48000.1, 48000)
    check_rate("Device D", 47999.9, 48000)
    check_rate("Device Upper Bound", 48000.4, 48000)
    check_rate("Device Half Round", 47999.5, 48000)


def test_check_rate_mismatch():
    with pytest.raises(SourceError) as exc_info:
        check_rate("Device A", 44100.0, 48000)

    assert exc_info.value.key == "device_rate_mismatch"
    assert exc_info.value.text == str(exc_info.value)
    assert "Device A runs at 44100 Hz, not 48000 Hz." in exc_info.value.text
    assert "Set it to 48000 Hz" in exc_info.value.text

    with pytest.raises(SourceError) as exc_info:
        check_rate("Device B", 48000.0, 44100)

    assert exc_info.value.key == "device_rate_mismatch"
    assert exc_info.value.text == str(exc_info.value)
    assert "Device B runs at 48000 Hz, not 44100 Hz." in exc_info.value.text
    assert "Set it to 44100 Hz" in exc_info.value.text


def test_check_rate_boundary_mismatch():
    # Just outside the rounding threshold for 48000 Hz
    with pytest.raises(SourceError) as exc_info:
        check_rate("Boundary Device", 47999.4, 48000)

    assert exc_info.value.key == "device_rate_mismatch"
    assert "Boundary Device runs at 47999 Hz, not 48000 Hz." in exc_info.value.text
    assert "never resamples while recording." in exc_info.value.text


def test_fake_spec_none(monkeypatch):
    monkeypatch.delenv("KUULAS_RECORDER_FAKE", raising=False)
    assert fake_spec() is None


def test_fake_spec_valid(tmp_path, monkeypatch):
    spec_file = tmp_path / "spec.json"
    data = {
        "devices": [
            {
                "index": 0,
                "name": "Test Mic",
                "channels": 1,
                "default_rate": 48000.0,
                "hostapi": "fake",
                "default": True,
            }
        ]
    }
    spec_file.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("KUULAS_RECORDER_FAKE", str(spec_file))

    assert fake_spec() == data


def test_fake_spec_missing_file(tmp_path, monkeypatch):
    missing_file = tmp_path / "non_existent_spec.json"
    monkeypatch.setenv("KUULAS_RECORDER_FAKE", str(missing_file))

    spec = fake_spec()
    assert spec is not None
    assert "devices" in spec
    assert spec["devices"][0]["name"] == "Fake Mic"


def test_fake_spec_invalid_json(tmp_path, monkeypatch):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("not json content", encoding="utf-8")
    monkeypatch.setenv("KUULAS_RECORDER_FAKE", str(invalid_file))

    spec = fake_spec()
    assert spec is not None
    assert "devices" in spec
    assert spec["devices"][0]["name"] == "Fake Mic"
