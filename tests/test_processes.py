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


def test_a_failed_probe_is_retried_not_cached(monkeypatch):
    """A transient failure (a sysctl timeout, a half-mounted /proc) must not be
    cached: the next call sees the token and stale jobs reconcile."""
    monkeypatch.delitem(processes._CACHE, "boot", raising=False)
    monkeypatch.setattr(processes, "_FAILED_PROBE_RETRY_S", 0.0)
    calls = []

    def probe():
        calls.append(1)
        return None if len(calls) == 1 else "this-boot"

    monkeypatch.setattr(processes, "_probe_boot_id", probe)
    assert processes.boot_id() is None
    assert processes.boot_id() == "this-boot"


def test_a_successful_probe_is_read_once(monkeypatch):
    monkeypatch.delitem(processes._CACHE, "boot", raising=False)
    calls = []

    def probe():
        calls.append(1)
        return "this-boot"

    monkeypatch.setattr(processes, "_probe_boot_id", probe)
    assert processes.boot_id() == processes.boot_id() == "this-boot"
    assert len(calls) == 1


def test_a_failed_probe_backs_off_before_retrying(monkeypatch):
    """A persistently failing probe must not stall every jobs listing: failures
    retry after a backoff, not on every call."""
    monkeypatch.delitem(processes._CACHE, "boot", raising=False)
    calls = []

    def probe():
        calls.append(1)

    monkeypatch.setattr(processes, "_probe_boot_id", probe)
    assert processes.boot_id() is None
    assert processes.boot_id() is None
    assert len(calls) == 1
