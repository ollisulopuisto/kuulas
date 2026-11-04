"""Tests for kuulas ctl (WP52 remote control)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import stub_podcast  # noqa: F401

from kuulas import ctl_discovery
from kuulas.ctl import CtlError, run_ctl


def test_ctl_not_running_raises(tmp_path: Path):
    with pytest.raises(CtlError) as exc_info:
        run_ctl(tmp_path, "state")
    assert "error.ctl.not_running" in str(exc_info.value.key)


def test_ctl_dead_process_cleans_and_raises(tmp_path: Path):
    ctl_discovery.write(tmp_path, 9999, "fake-tok", 999999)
    with patch("kuulas.ctl_discovery.is_alive", return_value=False):
        with pytest.raises(CtlError) as exc_info:
            run_ctl(tmp_path, "state")
        assert "error.ctl.process_dead" in str(exc_info.value.key)
    assert not ctl_discovery.discovery_path(tmp_path).exists()


def test_ctl_queries(tmp_path: Path):
    secret_token = "my-tok"  # noqa: S105
    ctl_discovery.write(tmp_path, 9999, secret_token, os.getpid())

    def fake_call(port, token, path, method="GET", body=None, timeout=10.0):
        assert port == 9999
        assert token == secret_token
        if path == "/api/state":
            return {"project": {"tracks": []}, "head": "h0"}
        if path == "/api/words":
            return {"words": []}
        if path == "/api/stats":
            return {"duration_s": 12.0}
        if path == "/api/undo":
            return {"moved": {"direction": "undo"}}
        if path == "/api/redo":
            return {"moved": {"direction": "redo"}}
        raise ValueError(path)

    with patch("kuulas.ctl.call_server", side_effect=fake_call):
        res_state = run_ctl(tmp_path, "state")
        assert res_state["head"] == "h0"

        res_words = run_ctl(tmp_path, "words")
        assert res_words == {"words": []}

        res_stats = run_ctl(tmp_path, "stats")
        assert res_stats["duration_s"] == 12.0

        res_undo = run_ctl(tmp_path, "undo")
        assert res_undo["moved"]["direction"] == "undo"

        res_redo = run_ctl(tmp_path, "redo")
        assert res_redo["moved"]["direction"] == "redo"


def test_ctl_routes_edit_and_command_via_catalog(tmp_path: Path):
    secret_token = "my-tok"  # noqa: S105
    ctl_discovery.write(tmp_path, 9999, secret_token, os.getpid())

    recorded_calls = []

    def fake_call(port, token, path, method="GET", body=None, timeout=10.0):
        recorded_calls.append((path, method, body))
        if path == "/api/commands":
            return {
                "commands": [
                    {"name": "split_clip", "via": "/api/edit"},
                    {"name": "auto_silence", "via": "/api/command"},
                ]
            }
        if path in ("/api/edit", "/api/command"):
            return {"ok": True, "path": path, "body": body}
        raise ValueError(path)

    with patch("kuulas.ctl.call_server", side_effect=fake_call):
        # 1. Edit
        res1 = run_ctl(tmp_path, "split_clip", {"clip_id": "c1", "at": 1000})
        assert res1["ok"] is True
        assert recorded_calls[-1] == (
            "/api/edit",
            "POST",
            {"op": "split_clip", "args": {"clip_id": "c1", "at": 1000}},
        )

        # 2. Command
        res2 = run_ctl(tmp_path, "auto_silence", {"margin_db": 6.0})
        assert res2["ok"] is True
        assert recorded_calls[-1] == (
            "/api/command",
            "POST",
            {"name": "auto_silence", "args": {"margin_db": 6.0}},
        )

        # 3. Unknown command
        with pytest.raises(CtlError) as exc_info:
            run_ctl(tmp_path, "nonexistent_op")
        assert "error.ctl.unknown_command" in str(exc_info.value.key)


def test_ctl_transport(tmp_path: Path):
    secret_token = "my-tok"  # noqa: S105
    ctl_discovery.write(tmp_path, 9999, secret_token, os.getpid())

    def fake_call(port, token, path, method="GET", body=None, timeout=10.0):
        assert path == "/api/transport"
        assert body == {"action": "stop"}
        return {"playing": False}

    with patch("kuulas.ctl.call_server", side_effect=fake_call):
        res = run_ctl(tmp_path, "transport", {"action": "stop"})
        assert res == {"playing": False}
