import json

from kuulas_recorder.sources import fake_spec


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
