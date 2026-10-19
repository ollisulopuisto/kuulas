"""Fuzzing and security hardening tests for server endpoints, operations, and file paths.

Tests cover:
- Host header validation & DNS rebinding checks.
- Origin header validation (preventing CSRF from foreign origins/null).
- Path traversal and path validation fuzzing.
- Malformed / unexpected payload types to API endpoints.
- Fuzzing operation names and args in /api/edit and /api/command.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from kuulas.server import create_app
from kuulas.session import Session


def create_test_client(tmp_path: Path):
    proj_dir = tmp_path / "FuzzTest.kuulas"
    session = Session(proj_dir)
    engine = MagicMock()
    engine.status.return_value = {
        "playing": False,
        "position": 0,
        "until": None,
        "notices": [],
    }
    engine.rate = 48000
    engine.meter.return_value = {
        "l": -60.0,
        "r": -60.0,
        "hold_l": -60.0,
        "hold_r": -60.0,
    }

    app = create_app(session, engine)
    client = TestClient(app)
    return client, session


def test_host_header_validation(tmp_path: Path):
    client, _ = create_test_client(tmp_path)

    # Allowed local host headers
    res = client.get("/api/state", headers={"Host": "127.0.0.1:8000"})
    assert res.status_code == 200

    res = client.get("/api/state", headers={"Host": "localhost:8000"})
    assert res.status_code == 200

    # Rejected host headers (DNS rebinding prevention)
    res = client.get("/api/state", headers={"Host": "evil.com"})
    assert res.status_code == 400
    assert "Invalid Host header" in res.json()["error"]["text"]

    res = client.get("/api/state", headers={"Host": "attacker.local:8000"})
    assert res.status_code == 400


def test_origin_header_validation(tmp_path: Path):
    client, _ = create_test_client(tmp_path)

    # Allowed local origins
    res = client.get("/api/state", headers={"Origin": "http://127.0.0.1:8000"})
    assert res.status_code == 200

    res = client.get("/api/state", headers={"Origin": "http://localhost:8000"})
    assert res.status_code == 200

    # Requests without Origin header (local app / curl / CLI ctl) pass through
    res = client.get("/api/state")
    assert res.status_code == 200

    # Foreign origins blocked with 403
    res = client.get("/api/state", headers={"Origin": "http://evil.com"})
    assert res.status_code == 403

    # Null origin blocked with 403
    res = client.get("/api/state", headers={"Origin": "null"})
    assert res.status_code == 403


def test_path_traversal_fuzzing(tmp_path: Path):
    client, _ = create_test_client(tmp_path)

    bad_paths = [
        "../../../../etc/passwd",
        "/etc/passwd",
        r"..\..\windows\system32",
        "project.kuulas/../../secret.txt",
        "\0/invalid/path",
        "A" * 5000,
        "",
        "   ",
    ]

    for path in bad_paths:
        # /api/project/open
        res = client.post("/api/project/open", json={"path": path})
        assert res.status_code in (400, 422)

        # /api/clipboard/project
        res = client.get("/api/clipboard/project", params={"path": path})
        assert res.status_code in (400, 422)

        # /api/media/locate
        res = client.post("/api/media/locate", json={"folder": path})
        assert res.status_code in (400, 422)


def test_invalid_json_fuzzing(tmp_path: Path):
    client, _ = create_test_client(tmp_path)

    # Invalid JSON bodies or wrong type primitives
    payloads = [
        {},
        {"op": None},
        {"op": 12345},
        {"op": "split", "args": "not_a_dict"},
        {"op": "split", "args": {"clip_ids": 12345}},
    ]

    for p in payloads:
        res = client.post("/api/edit", json=p)
        assert res.status_code == 400


def test_fuzz_ops_and_commands(tmp_path: Path):
    client, _ = create_test_client(tmp_path)

    # Non-existent or bad ops
    res = client.post("/api/edit", json={"op": "non_existent_op_xyz", "args": {}})
    assert res.status_code == 400
    assert res.json()["error"]["key"] == "error.edit.unknown"

    # Non-existent command
    res = client.post("/api/command", json={"name": "non_existent_command", "args": {}})
    assert res.status_code == 400

    # Fuzz arguments with random values
    fuzz_args = [
        {"clip_id": "../../../etc/passwd"},
        {"track_id": "invalid_track_id_999"},
        {"gain_db": "not_a_number"},
        {"fade_in": -999999},
        {"indices": [999999, -1]},
    ]

    for args in fuzz_args:
        res = client.post("/api/edit", json={"op": "set_clip", "args": args})
        assert res.status_code == 400

        res = client.post("/api/command", json={"name": "cut_words", "args": args})
        assert res.status_code == 400


def test_transport_and_peak_fuzzing(tmp_path: Path):
    client, _ = create_test_client(tmp_path)

    # Invalid action
    res = client.post("/api/transport", json={"action": "unknown_action"})
    assert res.status_code == 400

    # Seek/scrub missing 'at'
    res = client.post("/api/transport", json={"action": "seek"})
    assert res.status_code == 400

    # Invalid media peak tile query
    res = client.get("/api/peaks/non_existent_media/256/0")
    assert res.status_code == 404

    res = client.get("/api/candidates/non_existent_candidate/preview")
    assert res.status_code == 404
