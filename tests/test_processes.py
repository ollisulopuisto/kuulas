import os
import signal

import pytest

from kuulas import processes


def test_windows_pid_liveness_uses_process_query(monkeypatch):
    seen = []
    monkeypatch.setattr(processes.os, "name", "nt")
    monkeypatch.setattr(processes, "_windows_pid_alive",
                        lambda pid: seen.append(pid) or True)
    monkeypatch.setattr(processes.os, "kill",
                        lambda *_: pytest.fail("os.kill must not be used on Windows"))
    assert processes.pid_alive(os.getpid()) is True
    assert seen == [os.getpid()]


def test_windows_process_groups_and_signals_are_platform_specific(monkeypatch):
    monkeypatch.setattr(processes.os, "name", "nt")
    monkeypatch.setattr(processes.signal, "CTRL_C_EVENT", 0, raising=False)
    assert processes.process_group_options() == {"creationflags": 0x200}

    class Process:
        def __init__(self):
            self.sent = []

        def send_signal(self, sig):
            self.sent.append(sig)

        def terminate(self):
            self.sent.append("terminate")

        def kill(self):
            self.sent.append("kill")

    process = Process()
    processes.signal_process_group(process, signal.SIGINT)
    processes.signal_process_group(process, signal.SIGTERM)
    processes.signal_process_group(process, 9)
    assert process.sent == [0, "terminate", "kill"]
