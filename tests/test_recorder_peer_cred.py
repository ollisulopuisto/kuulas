"""Recorder socket peer credentials: refuse peers of another UID."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from kuulas_recorder.transport import UnixTransport


@pytest.fixture
def sock_path() -> Iterator[Path]:
    # AF_UNIX caps sun_path at 108 bytes: CI's pytest tmp_path can exceed it,
    # so the socket lives in a short directory of its own.
    folder = Path(tempfile.mkdtemp(prefix="kpc-"))
    try:
        yield folder / "rec.sock"
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_listener_accepts_same_uid_connection(sock_path: Path):
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


def test_listener_refuses_foreign_uid_connection(sock_path: Path):
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
