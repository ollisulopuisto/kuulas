"""Tests for the command-line client for a running Kuulas server."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kuulas import ctl_discovery
from kuulas.ctl import CtlError, run_ctl


def test_ctl_requires_running_project(tmp_path: Path):
    with pytest.raises(CtlError) as error:
        run_ctl(tmp_path, "state")
    assert error.value.key == "error.ctl.not_running"


def test_ctl_cleans_discovery_for_dead_server(tmp_path: Path):
    ctl_discovery.write(tmp_path, 9999, "token", 999999)
    with (patch("kuulas.ctl_discovery.is_alive", return_value=False),
          pytest.raises(CtlError) as error):
        run_ctl(tmp_path, "state")
    assert error.value.key == "error.ctl.process_dead"
    assert not ctl_discovery.discovery_path(tmp_path).exists()


def test_ctl_passes_token_and_routes_catalog_commands(tmp_path: Path):
    token = "secret-token"  # noqa: S105
    ctl_discovery.write(tmp_path, 9999, token, os.getpid())
    calls = []

    def fake_call(port, given_token, path, method="GET", body=None,
                  timeout=10.0):
        assert (port, given_token) == (9999, token)
        calls.append((path, method, body))
        if path == "/api/commands":
            return {"commands": [{"name": "split_clip", "via": "/api/edit"}]}
        return {"ok": True}

    with patch("kuulas.ctl.call_server", side_effect=fake_call):
        assert run_ctl(tmp_path, "split_clip", {"clip_id": "c1"}) == {"ok": True}
    assert calls[-1] == ("/api/edit", "POST",
                         {"op": "split_clip", "args": {"clip_id": "c1"}})


def test_ctl_rejects_unknown_commands(tmp_path: Path):
    ctl_discovery.write(tmp_path, 9999, "token", os.getpid())
    with (patch("kuulas.ctl.call_server", return_value={"commands": []}),
          pytest.raises(CtlError) as error):
        run_ctl(tmp_path, "not_a_command")
    assert error.value.key == "error.ctl.unknown_command"
