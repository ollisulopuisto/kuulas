"""Keep the machine awake while a take records.

macOS: ``caffeinate -i -m -w <supervisor pid>`` (a standard system tool):
``-i`` no idle sleep, ``-m`` no disk idle sleep, ``-w`` it exits by itself when
the supervisor exits, even after a SIGKILL, so it can never keep the machine
awake forever. Closing a laptop lid still sleeps the machine (macOS allows no
user process to stop that); docs/RECORDER.md says so.

Windows (later): ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``.
Linux: nothing yet (``systemd-inhibit`` would do it).
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger("kuulas_recorder")


class KeepAwake:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    @property
    def active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.active or sys.platform != "darwin":
            return
        tool = shutil.which("caffeinate")
        if tool is None:
            log.warning("caffeinate not found: the machine may sleep while recording")
            return
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
                [tool, "-i", "-m", "-w", str(os.getpid())],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except OSError as e:
            log.warning("could not start caffeinate: %s", e)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            with contextlib.suppress(OSError):
                proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                proc.wait(2)
