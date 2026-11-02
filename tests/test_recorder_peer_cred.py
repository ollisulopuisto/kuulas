"""Recorder socket peer credentials: refuse peers of another UID."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from kuulas_recorder.transport import UnixTransport


def test_listener_accepts_same_uid_connection():
    with tempfile.TemporaryDirectory(prefix="k-", dir=".") as directory:
        _assert_listener_accepts_same_uid_connection(Path(directory) / "rec.sock")


def _assert_listener_accepts_same_uid_connection(sock_path: Path):
    transport = UnixTransport()
    listener = transport.listen(sock_path)
    try:
        client = transport.connect(sock_path)
        srv_conn = listener.accept()
        assert srv_conn is not None
        srv_conn.close()
        client.close()
    finally:
        listener.close()


def test_listener_refuses_foreign_uid_connection():
    with tempfile.TemporaryDirectory(prefix="k-", dir=".") as directory:
        _assert_listener_refuses_foreign_uid_connection(Path(directory) / "rec.sock")


def _assert_listener_refuses_foreign_uid_connection(sock_path: Path):
    transport = UnixTransport()
    listener = transport.listen(sock_path)
    try:
        with patch("kuulas_recorder.transport.peer_uid", return_value=os.getuid() + 1):
            client = transport.connect(sock_path)
            srv_conn = listener.accept()
            assert srv_conn is None
            client.close()
    finally:
        listener.close()
