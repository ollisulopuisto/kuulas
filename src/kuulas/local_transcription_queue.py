"""One local model at a time across detached workers and project windows.

Tickets establish arrival order; the OS advisory lock is the final exclusion
barrier. The lock releases on process death, unlike a PID-only lock directory.
This is admission before the external tool's own guard, never a replacement for
that guard. No model is loaded while waiting; cancellation remains pollable.
"""
from __future__ import annotations

import contextlib
import os
import secrets
import threading
import time
from collections.abc import Iterator
from pathlib import Path

from .jobs import JobCancelledError
from .messages import config_dir
from .package import _pid_alive

POLL_S = 0.1


def _root() -> Path:
    override = os.environ.get('KUULAS_LOCAL_QUEUE_DIR')
    return Path(override) if override else config_dir() / 'local-transcription-queue'


@contextlib.contextmanager
def slot(cancel: threading.Event) -> Iterator[None]:
    """Wait in FIFO order without spawning a local model; release on every exit."""
    # Local Orukeet is Apple-silicon-only. Keep POSIX locking out of imports so
    # the editor and cloud workers still import on Windows.

    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    ticket = root / f'{time.time_ns():020d}-{os.getpid()}-{secrets.token_hex(4)}.wait'
    ticket.touch(exist_ok=False)
    try:
        with (root / 'active.lock').open('a+b') as lock:
            acquired = False
            while not acquired:
                if cancel.wait(POLL_S):
                    raise JobCancelledError
                waiting = []
                for item in root.glob('*.wait'):
                    try:
                        pid = int(item.name.split('-')[1])
                    except (ValueError, IndexError):
                        continue
                    if not _pid_alive(pid):
                        item.unlink(missing_ok=True)
                    else:
                        waiting.append(item.name)
                if waiting and ticket.name != min(waiting):
                    continue
                try:
                    _lock(lock, acquire=True)
                    acquired = True
                except BlockingIOError:
                    continue
            try:
                if cancel.is_set():
                    raise JobCancelledError
                yield
            finally:
                _lock(lock, acquire=False)
    finally:
        ticket.unlink(missing_ok=True)


def _lock(handle, *, acquire: bool) -> None:
    if os.name == "nt":
        import msvcrt  # noqa: PLC0415
        handle.seek(0)
        if acquire:
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(),
                          msvcrt.LK_NBLCK if acquire else msvcrt.LK_UNLCK, 1)
        except OSError as exc:
            raise BlockingIOError from exc
    else:
        import fcntl  # noqa: PLC0415
        fcntl.flock(handle.fileno(),
                    (fcntl.LOCK_EX | fcntl.LOCK_NB) if acquire else fcntl.LOCK_UN)
