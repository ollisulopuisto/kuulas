"""The UI's remembered settings live in a file in the user's config folder (they
were lost on every launch in browser storage: a fresh port per window)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from kuulas import ui_prefs
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture(autouse=True)
def prefs_file(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "cfg" / "ui-prefs.json"
    monkeypatch.setenv("KUULAS_UI_PREFS_FILE", str(path))
    return path


def _client(tmp_path: Path) -> TestClient:
    engine = MagicMock()
    engine.status.return_value = {
        "playing": False, "position": 0, "until": None, "notices": []}
    engine.rate = 48000
    return TestClient(create_app(Session(tmp_path / "P.kuulas"), engine))


def test_missing_file_is_empty():
    assert ui_prefs.load() == {}


def test_corrupt_file_is_empty_and_can_be_overwritten(prefs_file: Path):
    prefs_file.parent.mkdir(parents=True)
    prefs_file.write_text("{not json", encoding="utf-8")
    assert ui_prefs.load() == {}
    assert ui_prefs.update(set_={"kuulas.fast": "1.75"}) == {"kuulas.fast": "1.75"}


def test_non_string_values_in_the_file_are_dropped(prefs_file: Path):
    prefs_file.parent.mkdir(parents=True)
    prefs_file.write_text(json.dumps({"kuulas.a": "x", "kuulas.b": 3, "bad key!": "y"}))
    assert ui_prefs.load() == {"kuulas.a": "x"}


def test_set_and_remove_persist(prefs_file: Path):
    ui_prefs.update(set_={"kuulas.a": "1", "kuulas.b": "2"})
    ui_prefs.update(remove=["kuulas.a"])
    assert json.loads(prefs_file.read_text(encoding="utf-8")) == {"kuulas.b": "2"}


def test_write_is_atomic_no_temp_left(prefs_file: Path):
    ui_prefs.update(set_={"kuulas.a": "1"})
    assert [p.name for p in prefs_file.parent.iterdir()] == ["ui-prefs.json"]


def test_bad_keys_and_values_are_refused():
    for bad in ({"other.thing": "1"}, {"kuulas.a": 3}, {"kuulas.a": "x" * 20000},
                {"k" * 300: "1"}, {"": "1"}):
        with pytest.raises(ui_prefs.PrefsError):
            ui_prefs.update(set_=bad)


def test_size_cap_refuses_growth(monkeypatch):
    monkeypatch.setattr(ui_prefs, "MAX_BYTES", 200)
    ui_prefs.update(set_={"kuulas.a": "x" * 100})
    with pytest.raises(ui_prefs.PrefsError):
        ui_prefs.update(set_={"kuulas.b": "y" * 150})
    assert ui_prefs.load() == {"kuulas.a": "x" * 100}


def test_endpoints_round_trip(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/api/prefs").json() == {"prefs": {}}
    res = client.put("/api/prefs", json={"set": {"kuulas.fast": '{"speed":1.75}'}})
    assert res.status_code == 200
    assert client.get("/api/prefs").json() == {"prefs": {"kuulas.fast": '{"speed":1.75}'}}
    client.put("/api/prefs", json={"remove": ["kuulas.fast"]})
    assert client.get("/api/prefs").json() == {"prefs": {}}


def test_endpoint_refuses_bad_input(tmp_path: Path):
    client = _client(tmp_path)
    assert client.put("/api/prefs", json={"set": {"evil!": 1}}).status_code == 400
    assert client.put("/api/prefs", json={"set": []}).status_code == 400


def test_foreign_origin_and_host_are_refused(tmp_path: Path):
    client = _client(tmp_path)
    evil = {"Origin": "https://evil.example"}
    assert client.get("/api/prefs", headers=evil).status_code == 403
    body = {"set": {"kuulas.a": "1"}}
    assert client.put("/api/prefs", json=body, headers=evil).status_code == 403
    assert client.get("/api/prefs", headers={"Host": "evil.example"}).status_code == 400
    assert ui_prefs.load() == {}
