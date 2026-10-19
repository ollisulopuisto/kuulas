"""A client for the recorder's control protocol (the editor uses this; so do tests).

    with RecorderClient.connect() as rec:
        rec.request("hello", subscribe=True)
        rec.request("start", folder=..., take="take-001", channels=[1], names=["Olli"])
        ev = rec.next_event(timeout=1.0)

``spawn_supervisor`` starts the recorder as its own session (``setsid``), with
no tie to the caller's terminal or process group, so the editor quitting or
crashing does not stop it.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from kuulas_recorder.transport import Connection, UnixTransport, default_socket_path


class RecorderError(Exception):
    """An error answer from the recorder, with its stable ``key``."""

    def __init__(self, key: str, text: str):
        super().__init__(f"{key}: {text}")
        self.key = key
        self.text = text


class RecorderClient:
    def __init__(self, conn: Connection, timeout: float = 30.0):
        self.conn = conn
        self.timeout = timeout
        self.events: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self._answers: dict[int, dict] = {}
        self._cv = threading.Condition()
        self.closed = False
        self._thread = threading.Thread(target=self._read, name="recorder-client",
                                        daemon=True)
        self._thread.start()

    @classmethod
    def connect(cls, path: Path | str | None = None, *, timeout: float = 30.0,
                transport=None) -> RecorderClient:
        t = transport or UnixTransport()
        return cls(t.connect(Path(path) if path else default_socket_path()), timeout)

    def __enter__(self) -> RecorderClient:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _read(self) -> None:
        while True:
            line = self.conn.read_line()
            if line is None:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "event" in msg:
                self.events.put(msg)
                continue
            with self._cv:
                self._answers[msg.get("id")] = msg
                self._cv.notify_all()
        with self._cv:
            self.closed = True
            self._cv.notify_all()

    def request(self, cmd: str, timeout: float | None = None, **args) -> dict:
        """Send one command and wait for its answer; an error answer raises."""
        rid = next(self._ids)
        self.conn.send(json.dumps({"id": rid, "cmd": cmd, **args}).encode() + b"\n")
        deadline = time.monotonic() + (timeout or self.timeout)
        with self._cv:
            while rid not in self._answers:
                left = deadline - time.monotonic()
                if self.closed:
                    raise RecorderError("disconnected", "The recorder closed the "
                                        "connection.")
                if left <= 0:
                    raise RecorderError("timeout", f"No answer to {cmd} in time.")
                self._cv.wait(left)
            msg = self._answers.pop(rid)
        if not msg.get("ok"):
            err = msg.get("error") or {}
            raise RecorderError(err.get("key", "unknown"), err.get("text", ""))
        return msg

    def next_event(self, timeout: float | None = None) -> dict | None:
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def wait_event(self, name: str, timeout: float = 10.0) -> dict:
        """The next event called ``name``; other events are dropped."""
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RecorderError("timeout", f"No {name} event in time.")
            ev = self.next_event(left)
            if ev is not None and ev["event"] == name:
                return ev

    def close(self) -> None:
        self.conn.close()


def spawn_supervisor(socket_path: Path | str | None = None, *,
                     state_dir: Path | str | None = None, extra: list[str] = (),
                     env: dict | None = None, wait: float = 10.0) -> subprocess.Popen:
    """Start ``kuulas-recorder serve`` detached from the caller, and wait until it
    answers. It keeps running after the caller exits."""
    path = Path(socket_path) if socket_path else default_socket_path()
    argv = [sys.executable, "-m", "kuulas_recorder", "serve", "--socket", str(path)]
    if state_dir:
        argv += ["--state-dir", str(state_dir)]
    argv += list(extra)
    proc = subprocess.Popen(  # noqa: S603 - our own module, fixed argv
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
        env=env if env is not None else os.environ.copy())
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RecorderError("spawn_failed",
                                f"The recorder exited at once (code {proc.returncode}).")
        with contextlib.suppress(OSError):
            UnixTransport().connect(path, timeout=1.0).close()
            return proc
        time.sleep(0.05)
    raise RecorderError("spawn_failed", "The recorder did not start listening in time.")
