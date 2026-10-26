"""Signing in to Google for Colab, without ever blocking the editor.

Colab needs a Google sign-in that is interactive: the tool prints an address, the user
signs in in the browser and pastes back the code Google shows. A detached transcription
worker has no terminal, so the sign-in happens here, before a job exists:

* :func:`signed_in` is the cheap preflight (no network, no upload): does the Colab CLI's
  own store hold a token it can refresh? Only the store's *shape* is read; nothing of it
  is returned, logged or sent anywhere.
* :class:`SigninFlow` runs the tool's login command (``<colab-transcribe> --login``, which
  runs ``colab usage``) in the background. The editor shows its output and the address
  (also opened in the browser), takes the pasted code in a text field and writes it to
  the tool's standard input, then checks :func:`signed_in` again.

The credentials stay in the tool's own store (``~/.config/colab-cli/token.json``). The
pasted code is a one-time value: it is passed to the process and not stored, logged or
put on a command line.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import signal
import subprocess
import threading
import webbrowser
from collections import deque
from pathlib import Path

from . import processes, toolpath
from .colab_transcribe import ColabError
from .messages import t

log = logging.getLogger("kuulas.colab_signin")

#: The sign-in may take a while (a browser, a password manager, two-step verification).
TIMEOUT_S = 600
LINES_SHOWN = 30
TAIL_LINES = 8
_ADDRESS = re.compile(r"https://accounts\.google\.com/\S+")
#: What a pasted authorization code may look like: one word of URL-safe characters.
_CODE = re.compile(r"[A-Za-z0-9._~/+=-]{1,1024}")


class SigninError(ColabError):
    """A refused sign-in request (a message key)."""


def token_path() -> Path:
    """``$KUULAS_COLAB_TOKEN`` (tests) or the Colab CLI's token file."""
    override = os.environ.get("KUULAS_COLAB_TOKEN")
    if override:
        return Path(override)
    return Path.home() / ".config" / "colab-cli" / "token.json"


def signed_in() -> bool:
    """Whether the Colab CLI has a token it can use (or renew): the file exists, is a
    JSON object and has a refresh token. Reads nothing else, returns nothing of it."""
    try:
        data = json.loads(token_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    refresh = data.get("refresh_token") if isinstance(data, dict) else None
    return isinstance(refresh, str) and bool(refresh)


def open_url(url: str) -> None:
    """Open the sign-in address in the user's browser (tests replace this)."""
    webbrowser.open(url)


def _error(key: str, **params) -> dict:
    return {"key": key, "params": params, "text": str(t(key, **params))}


class SigninFlow:
    """One sign-in process at a time; ``status()`` is what ``/api/colab/signin`` says."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._state = "idle"
        self._url: str | None = None
        self._error: dict | None = None
        self._cancelled = False
        self._lines: deque[str] = deque(maxlen=LINES_SHOWN)

    def status(self) -> dict:
        with self._lock:
            return {"state": self._state, "url": self._url,
                    "lines": list(self._lines), "error": self._error,
                    "signed_in": signed_in()}

    def start(self, command: list[str], cwd: str | None) -> None:
        """Run ``command --login``. Does nothing while a sign-in is already running."""
        with self._lock:
            if self._state == "running":
                return
            self._state, self._url, self._error = "running", None, None
            self._cancelled = False
            self._lines.clear()
        cmd = [*command, "--login"]
        program = toolpath.resolve(cmd[0])
        if program is None:
            self._fail(_error("error.colab.not_found", command=" ".join(command),
                              cwd=cwd or ""))
            return
        try:
            proc = subprocess.Popen(  # noqa: S603 - an argument list from settings
                [program, *cmd[1:]], cwd=cwd, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                errors="replace", bufsize=1, env=toolpath.tool_env(),
                **processes.process_group_options())
        except OSError:
            self._fail(_error("error.colab.not_found", command=" ".join(command),
                              cwd=cwd or ""))
            return
        with self._lock:
            self._proc = proc
        reader = threading.Thread(target=self._read, args=(proc,), daemon=True,
                                  name="kuulas-colab-signin")
        reader.start()
        timer = threading.Timer(TIMEOUT_S, self._stop, args=(proc,))
        timer.daemon = True
        timer.start()
        threading.Thread(target=self._finish, args=(proc, timer, reader), daemon=True,
                         name="kuulas-colab-signin-wait").start()

    def _read(self, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            found = _ADDRESS.search(line)
            with self._lock:
                self._lines.append(line)
                first = found is not None and self._url is None
                if first and found is not None:
                    self._url = found.group(0)
            if first and found is not None:
                with contextlib.suppress(Exception):  # no browser: the dialog shows it
                    open_url(found.group(0))

    def _finish(self, proc: subprocess.Popen, timer: threading.Timer,
                reader: threading.Thread) -> None:
        proc.wait()
        timer.cancel()
        reader.join(timeout=2)  # the reader takes the last lines first
        with self._lock:
            cancelled = self._cancelled
            tail = "\n".join(list(self._lines)[-TAIL_LINES:])
        if cancelled:
            with self._lock:
                self._state = "cancelled"
        elif proc.returncode == 0 and signed_in():
            with self._lock:
                self._state = "done"
        else:
            self._fail(_error("error.colab.signin_failed", code=proc.returncode,
                              tail=tail))

    def _fail(self, error: dict) -> None:
        with self._lock:
            self._state, self._error = "failed", error

    def submit_code(self, code: str) -> None:
        """Give the pasted authorization code to the running login. Raises
        ``SigninError``; the value is not kept or logged."""
        code = (code or "").strip()
        if not _CODE.fullmatch(code):
            raise SigninError("error.colab.signin_bad_code")
        with self._lock:
            proc = self._proc if self._state == "running" else None
        if proc is None or proc.stdin is None:
            raise SigninError("error.colab.signin_not_running")
        try:
            proc.stdin.write(code + "\n")
            proc.stdin.flush()
        except (OSError, ValueError) as e:
            raise SigninError("error.colab.signin_not_running") from e

    def _stop(self, proc: subprocess.Popen) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            processes.signal_process_group(proc, signal.SIGTERM)

    def cancel(self) -> None:
        with self._lock:
            proc = self._proc if self._state == "running" else None
            self._cancelled = True
        if proc is not None:
            self._stop(proc)
