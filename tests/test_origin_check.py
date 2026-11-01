"""A page on another site must not be able to drive the local server (Origin check)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kuulas.server import create_app
from kuulas.session import Session


def _client(tmp_path: Path) -> TestClient:
    session = Session(tmp_path / "Origin.kuulas")
    engine = MagicMock()
    engine.status.return_value = {
        "playing": False, "position": 0, "until": None, "notices": []}
    engine.rate = 48000
    return TestClient(create_app(session, engine))


def test_a_foreign_origin_is_refused_on_a_write(tmp_path: Path):
    res = _client(tmp_path).post(
        "/api/transport", json={"action": "pause"}, headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_a_foreign_origin_is_refused_on_a_read_too(tmp_path: Path):
    res = _client(tmp_path).get("/api/state", headers={"Origin": "https://evil.example"})
    assert res.status_code == 403


def test_origin_null_is_refused_on_a_write(tmp_path: Path):
    res = _client(tmp_path).post(
        "/api/transport", json={"action": "pause"}, headers={"Origin": "null"})
    assert res.status_code == 403


def test_the_apps_own_origin_and_no_origin_pass(tmp_path: Path):
    client = _client(tmp_path)
    for origin in ("http://127.0.0.1:8765", "http://localhost:8765", "http://[::1]:8765"):
        assert client.get("/api/state", headers={"Origin": origin}).status_code == 200
    assert client.get("/api/state").status_code == 200


def test_live_websocket_refuses_foreign_origin(tmp_path: Path):
    client = _client(tmp_path)
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(
        "/api/live", headers={"Origin": "https://evil.example"}
    ):
        pass
    assert exc.value.code in (1008, 4403)


def test_live_websocket_refuses_foreign_host(tmp_path: Path):
    client = _client(tmp_path)
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect(
        "/api/live", headers={"Host": "evil.example"}
    ):
        pass
    assert exc.value.code in (1008, 4403)


def test_live_websocket_allows_loopback_origin_and_no_origin(tmp_path: Path):
    client = _client(tmp_path)
    with client.websocket_connect(
        "/api/live", headers={"Origin": "http://127.0.0.1:8765"}
    ) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "hello"

    with client.websocket_connect("/api/live") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "hello"
