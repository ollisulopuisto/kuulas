"""The local transport under the control protocol: a Unix domain socket.

Kept behind ``Listener`` and ``Connection`` so a Windows named pipe can be
added without touching the supervisor or the client: both only use
``accept``, ``read_line``, ``send`` and ``close``.

The socket path: macOS limits a socket path to 104 bytes (Linux: 108), so it
lives in a short per-user folder:

- ``KUULAS_RECORDER_SOCKET`` if set;
- macOS: ``~/Library/Application Support/kuulas/recorder/rec.sock``;
- Linux: ``$XDG_RUNTIME_DIR/kuulas/rec.sock``, else ``~/.local/state/kuulas/rec.sock``;
- if that is too long (a very long home path), ``/tmp/kuulas-<uid>/rec.sock``.

The folder is created with mode 0700 and the socket is 0600: only the user
who runs the recorder can talk to it.
"""

from __future__ import annotations

import contextlib
import os
import socket
import struct
import sys
from pathlib import Path

SOCKET_ENV = "KUULAS_RECORDER_SOCKET"
MAX_LINE = 1 << 20  # a command line longer than this is refused


def _sun_path_limit() -> int:
    return 104 if sys.platform == "darwin" else 108


def peer_uid(sock: socket.socket) -> int | None:
    """The UID of the peer process at the other end of a Unix domain socket, or None."""
    if hasattr(socket, "SO_PEERCRED"):
        try:
            cred = sock.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", cred)
        except (OSError, struct.error):
            return None
        else:
            return uid
    if sys.platform == "darwin":
        try:
            cred = sock.getsockopt(0, 1, 16)  # SOL_LOCAL=0, LOCAL_PEERCRED=1
            _version, uid = struct.unpack("II", cred[:8])
        except (OSError, struct.error):
            return None
        else:
            return uid
    return None


def default_socket_path() -> Path:
    env = os.environ.get(SOCKET_ENV)
    if env:
        return Path(env)
    home = Path.home()
    if sys.platform == "darwin":
        support = home / "Library" / "Application Support"
        path = support / "kuulas" / "recorder" / "rec.sock"
    else:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        base = Path(runtime) if runtime else home / ".local" / "state"
        path = base / "kuulas" / "rec.sock"
    if len(os.fsencode(path)) >= _sun_path_limit():
        path = Path("/tmp") / f"kuulas-{os.getuid()}" / "rec.sock"  # noqa: S108 - 0700 folder, see above
    return path


class Connection:
    """One client connection: newline-delimited byte lines."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._file = sock.makefile("rb")
        self._send_timeout: float | None = None

    def read_line(self) -> bytes | None:
        """The next line without its newline, or None when the peer closed.
        A line over ``MAX_LINE`` closes the connection."""
        try:
            line = self._file.readline(MAX_LINE + 1)
        except (OSError, ValueError):
            return None
        if not line:
            return None
        if not line.endswith(b"\n"):
            if len(line) > MAX_LINE:
                return None
            return line  # the peer closed after a last line without newline
        return line[:-1]

    def send(self, data: bytes, timeout: float | None = None) -> None:
        """Send all of ``data``; with ``timeout``, raise ``OSError`` if the peer
        stops reading for that long. The timeout is the kernel's send timeout
        (``SO_SNDTIMEO``): ``socket.settimeout`` would also cut the reads of a
        client that is only quiet."""
        if timeout != self._send_timeout:
            sec = int(timeout or 0)
            usec = int(((timeout or 0) - sec) * 1_000_000)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO,
                                 struct.pack("ll", sec, usec))
            self._send_timeout = timeout
        self.sock.sendall(data)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            self._file.close()
        with contextlib.suppress(OSError):
            self.sock.close()


class Listener:
    def __init__(self, sock: socket.socket, path: Path):
        self.sock = sock
        self.path = path

    def accept(self) -> Connection | None:
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return None  # closed
        # Refuse connections from peers running under a different user account.
        p_uid = peer_uid(conn)
        if p_uid is not None and p_uid != os.getuid():
            with contextlib.suppress(OSError):
                conn.close()
            return None
        return Connection(conn)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()
        with contextlib.suppress(OSError):
            self.path.unlink()


class UnixTransport:
    """Unix domain socket transport (macOS, Linux)."""

    def listen(self, path: Path) -> Listener:
        """Bind ``path``. The caller holds the single-instance lock, so a socket
        file already there is stale (a killed recorder) and is replaced."""
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old = os.umask(0o177)
        try:
            sock.bind(os.fspath(path))
        finally:
            os.umask(old)
        sock.listen(16)
        return Listener(sock, path)

    def connect(self, path: Path, timeout: float = 5.0) -> Connection:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(os.fspath(path))
        except OSError:
            sock.close()
            raise
        sock.settimeout(None)
        return Connection(sock)
