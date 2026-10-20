"""A worker that crashed or was killed (Jetsam, the memory ceiling) must never
be answered by running the analysis in the editor: that is the memory the
worker was there to keep out of it (docs/MEMORY.md). Only a worker that could
not be STARTED falls back inline, one at a time, gated, and not when the
editor is already big. Fake Popen; no process is started."""

import logging
import pickle
import threading
import time
from pathlib import Path

import pytest

from kuulas import memory as kmemory
from kuulas import offload, priority
from kuulas.messages import KuulasError


class FakeProc:
    """A child that exits with ``code`` at once, optionally writing a reply."""

    def __init__(self, argv, code, reply=None, raw=None):
        self.pid, self.stdin, self.returncode = 4242, None, None
        self._code = code
        if reply is not None:
            Path(argv[-1]).write_bytes(pickle.dumps(reply))
        if raw is not None:
            Path(argv[-1]).write_bytes(raw)

    def wait(self, timeout=None):
        self.returncode = self._code
        return self._code

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = self._code


@pytest.fixture
def calls(monkeypatch):
    seen = {"fn": 0, "running": 0, "most": 0}
    lock = threading.Lock()

    def fn(_project, _store, *_a, **_k):
        with lock:
            seen["fn"] += 1
            seen["running"] += 1
            seen["most"] = max(seen["most"], seen["running"])
        time.sleep(0.02)
        with lock:
            seen["running"] -= 1
        return "inline-answer"

    monkeypatch.setattr(offload, "MODE", "process")
    monkeypatch.setattr(offload, "resolve", lambda _task: fn)
    monkeypatch.setattr(offload, "store_spec", lambda _s: {"folder": "/p"})
    monkeypatch.setattr(offload.rss, "current", lambda: 1024**3)
    return seen


def manager_with(monkeypatch, popen):
    m = offload.WorkerManager(poll_s=0.01, watch_s=0.05, popen=popen)
    monkeypatch.setattr(offload, "MANAGER", m)
    return m


def crash(code, **kw):
    return lambda argv, **_o: FakeProc(argv, code, **kw)


def cannot_start(exc=None):
    def popen(_argv, **_o):
        raise exc or FileNotFoundError("no python")

    return popen


def test_a_crashed_worker_is_not_answered_inline(calls, monkeypatch):
    m = manager_with(monkeypatch, crash(1))
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.crashed"
    assert calls["fn"] == 0
    assert m.backoff_left(("crash", "silence_ranges", "/p")) > 0


def test_after_a_crash_the_next_call_backs_off_without_a_worker(calls, monkeypatch):
    started = []

    def popen(argv, **_o):
        started.append(1)
        return FakeProc(argv, 1)

    manager_with(monkeypatch, popen)
    with pytest.raises(KuulasError):
        offload.call("silence_ranges", None, None)
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.backoff"
    assert len(started) == 1
    assert calls["fn"] == 0


@pytest.mark.parametrize("code", [-9, 137, 9])
def test_a_memory_kill_is_named_in_the_log(calls, monkeypatch, caplog, code):
    manager_with(monkeypatch, crash(code))
    with caplog.at_level(logging.WARNING, logger="kuulas.offload"), \
            pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.crashed"
    assert any("memory" in r.getMessage().lower() for r in caplog.records)
    assert calls["fn"] == 0


def test_a_signal_death_names_the_signal(calls, monkeypatch):
    manager_with(monkeypatch, crash(-9))
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert "SIGKILL" in str(e.value.params.get("exit"))


def test_a_missing_or_corrupt_reply_is_a_crash(calls, monkeypatch):
    manager_with(monkeypatch, crash(0, raw=b"not a pickle"))
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.crashed"
    manager_with(monkeypatch, crash(0))
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.crashed"
    assert calls["fn"] == 0


def test_ten_concurrent_calls_after_a_crash_run_nothing_inline(calls, monkeypatch):
    manager_with(monkeypatch, crash(-9))
    with pytest.raises(KuulasError):
        offload.call("silence_ranges", None, None)
    errors = []

    def one():
        try:
            offload.call("silence_ranges", None, None)
        except KuulasError as e:
            errors.append(e.key)

    threads = [threading.Thread(target=one) for _ in range(10)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(10)
    assert len(errors) == 10
    assert calls["fn"] == 0


def test_a_worker_that_cannot_start_runs_inline_once(calls, monkeypatch, caplog):
    manager_with(monkeypatch, cannot_start())
    with caplog.at_level(logging.WARNING, logger="kuulas.offload"):
        got = offload.call("silence_ranges", None, None)
    assert got == "inline-answer"
    assert calls["fn"] == 1
    assert offload.INLINE["runs"] >= 1
    assert any("editor process" in r.getMessage() for r in caplog.records)


def test_start_failures_run_inline_one_at_a_time(calls, monkeypatch):
    manager_with(monkeypatch, cannot_start(PermissionError("denied")))
    threads = [threading.Thread(target=lambda: offload.call("silence_ranges", None, None))
               for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(10)
    assert calls["fn"] >= 1
    assert calls["most"] == 1


def test_inline_fallback_is_refused_when_the_editor_is_already_big(calls, monkeypatch):
    manager_with(monkeypatch, cannot_start(OSError("cannot fork")))
    monkeypatch.setattr(offload.rss, "current", lambda: kmemory.RSS_WARN_BYTES + 1)
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.memory"
    assert calls["fn"] == 0


def test_inline_fallback_waits_at_the_priority_gate(calls, monkeypatch):
    manager_with(monkeypatch, cannot_start(OSError("cannot fork")))
    seen = []
    monkeypatch.setattr(priority, "checkpoint", lambda *_a, **_k: seen.append(1))
    offload.call("silence_ranges", None, None)
    assert seen


def test_the_memory_ceiling_error_still_comes_back_with_its_key(calls, monkeypatch):
    reply = {"error": {"key": "error.offload.memory", "module": "kuulas.messages",
                       "cls": "KuulasError", "params": {"mb": 2000, "limit_mb": 1536}}}
    m = manager_with(monkeypatch, crash(0, reply=reply))
    with pytest.raises(KuulasError) as e:
        offload.call("silence_ranges", None, None)
    assert e.value.key == "error.offload.memory"
    assert m.backoff_left(("memory", "silence_ranges", "/p")) > 0
    assert calls["fn"] == 0
