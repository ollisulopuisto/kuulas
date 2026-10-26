"""Tests for the running-window discovery file."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kuulas.ctl_discovery import (
    check_token,
    discovery_path,
    is_alive,
    new_token,
    read,
    remove,
    write,
)


class TestDiscoveryPath:
    def test_returns_ctl_json_under_folder(self, tmp_path: Path):
        assert discovery_path(tmp_path) == tmp_path / "ctl.json"


class TestNewToken:
    def test_is_url_safe_and_long(self):
        token = new_token()
        assert isinstance(token, str)
        assert len(token) >= 32
        assert set(token).issubset(
            set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        )

    def test_tokens_differ(self):
        assert new_token() != new_token()


class TestWriteAndRead:
    def test_round_trip(self, tmp_path: Path):
        write(tmp_path, 9000, "abc", 1234)
        info = read(tmp_path)
        assert info is not None
        assert info["port"] == 9000
        assert info["token"] == "abc"  # noqa: S105
        assert info["pid"] == 1234
        assert isinstance(info["started_utc"], str)
        assert info["started_utc"].endswith("Z")

    @pytest.mark.skipif(os.name == "nt", reason="Windows uses inherited file ACLs")
    def test_file_mode_is_0600(self, tmp_path: Path):
        write(tmp_path, 9000, "abc", 1234)
        path = discovery_path(tmp_path)
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_atomic_replace(self, tmp_path: Path):
        write(tmp_path, 9000, "first", 1234)
        path = discovery_path(tmp_path)
        inode_before = path.stat().st_ino
        write(tmp_path, 9001, "second", 1235)
        info = read(tmp_path)
        assert info is not None
        assert info["port"] == 9001
        assert info["token"] == "second"  # noqa: S105
        assert info["pid"] == 1235
        assert path.stat().st_ino != inode_before


class TestReadErrors:
    def test_missing_file_returns_none(self, tmp_path: Path):
        assert read(tmp_path) is None

    def test_corrupt_json_returns_none(self, tmp_path: Path):
        path = discovery_path(tmp_path)
        path.write_text("not json", encoding="utf-8")
        assert read(tmp_path) is None

    def test_missing_field_returns_none(self, tmp_path: Path):
        path = discovery_path(tmp_path)
        path.write_text(json.dumps({"port": 9000, "token": "abc"}), encoding="utf-8")
        assert read(tmp_path) is None

    def test_wrong_type_returns_none(self, tmp_path: Path):
        path = discovery_path(tmp_path)
        payload = {
            "port": "9000",
            "token": "abc",
            "pid": 1234,
            "started_utc": "2026-10-18T10:00:00Z",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert read(tmp_path) is None


class TestIsAlive:
    def test_current_process_is_alive(self):
        assert is_alive({"pid": os.getpid()}) is True

    def test_non_positive_pid_is_not_alive(self):
        assert is_alive({"pid": 0}) is False
        assert is_alive({"pid": -1}) is False

    def test_dead_child_is_not_alive(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        assert is_alive({"pid": proc.pid}) is False


class TestCheckToken:
    def test_right_token(self):
        info = {"token": "secret"}
        assert check_token(info, "secret") is True

    def test_wrong_token(self):
        info = {"token": "secret"}
        assert check_token(info, "wrong") is False

    def test_missing_given(self):
        info = {"token": "secret"}
        assert check_token(info, None) is False

    def test_non_string_given(self):
        info = {"token": "secret"}
        assert check_token(info, 123) is False


class TestRemove:
    def test_deletes_existing_file(self, tmp_path: Path):
        write(tmp_path, 9000, "abc", 1234)
        remove(tmp_path)
        assert not discovery_path(tmp_path).exists()

    def test_missing_file_is_ignored(self, tmp_path: Path):
        remove(tmp_path)
        assert not discovery_path(tmp_path).exists()
