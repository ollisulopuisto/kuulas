"""At most one analysis worker process, and none left behind (owner's btop,
v26.10.20.2: ~35 stopped ``Kuulas -m kuulas.analysis_worker`` processes and the
Mac out of memory). The UI asks for loudness curves after every edit and aborts
the older request, but the server never saw the abort: each request started its
own worker, which was stopped (SIGSTOP) while audio played, and nothing reaped
them. These tests start real tiny child processes; no audio."""

import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
import uuid

import pytest

from kuulas import offload, priority
from kuulas.messages import KuulasError

SLEEPER = "import sys, time; time.sleep(float(sys.argv[1]))"


@pytest.fixture
def marker():
    return f"kuulas-test-{uuid.uuid4().hex}"


def sleeper(marker, seconds=30.0):
    return [sys.executable, "-c", SLEEPER, str(seconds), marker]


def children(marker) -> list[int]:
    """Live or unreaped children of this process whose command line has
    ``marker`` (zombies too: an unreaped child is a leak as well)."""
    out = subprocess.run(["ps", "-ax", "-o", "pid=,ppid=,stat=,command="],  # noqa: S607
                         capture_output=True, text=True, check=True).stdout
    me = os.getpid()
    found = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        pid, ppid, stat = int(parts[0]), int(parts[1]), parts[2]
        command = parts[3] if len(parts) > 3 else ""
        if ppid == me and (marker in command or stat.startswith("Z")):
            found.append(pid)
    return found


def any_with(marker) -> list[int]:
    out = subprocess.run(["ps", "-ax", "-o", "pid=,command="], capture_output=True,  # noqa: S607
                         text=True, check=True).stdout
    return [int(line.split(None, 1)[0]) for line in out.splitlines()
            if marker in line and "ps -ax" not in line]


def wait_for(cond, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture
def gate(monkeypatch):
    state = {"playing": False}
    g = priority.PlaybackGate(hold_s=0.0, poll_s=0.01)
    g.watch(lambda: state["playing"])
    monkeypatch.setattr(priority, "GATE", g)
    return state


@pytest.fixture
def manager():
    m = offload.WorkerManager(poll_s=0.01, watch_s=0.05)
    yield m
    m.shutdown()


class Sampler:
    """Counts this process's marked children every few ms; the maximum seen."""

    def __init__(self, marker):
        self.marker, self.most, self._stop = marker, 0, threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.most = max(self.most, len(children(self.marker)))
            time.sleep(0.005)

    def stop(self):
        self._stop.set()
        self._thread.join(5)
        return self.most


def in_threads(n, fn):
    results = [None] * n

    def one(i):
        try:
            results[i] = ("ok", fn(i))
        except BaseException as e:  # noqa: BLE001 - the test reads it
            results[i] = ("error", e)

    threads = [threading.Thread(target=one, args=(i,), daemon=True) for i in range(n)]
    for th in threads:
        th.start()
    return threads, results


def test_a_burst_of_curve_requests_while_playing_starts_no_worker(gate, manager, marker):
    gate["playing"] = True
    sampler = Sampler(marker)
    threads, results = in_threads(50, lambda _i: manager.run(
        sleeper(marker, 0.2), key="curves", pause=True))
    time.sleep(1.0)
    assert children(marker) == []  # deferred while playing, not started and stopped
    # Every request but the newest has been superseded already.
    assert wait_for(lambda: sum(r is not None for r in results) == 49)
    assert all(isinstance(r[1], offload.SupersededError)
               for r in results if r is not None)
    gate["playing"] = False
    for th in threads:
        th.join(15)
    assert sampler.stop() <= 1
    assert sum(r[0] == "ok" for r in results) == 1
    assert children(marker) == []


def test_never_more_than_one_worker_at_a_time(gate, manager, marker):
    sampler = Sampler(marker)
    threads, results = in_threads(6, lambda _i: manager.run(sleeper(marker, 0.15)))
    for th in threads:
        th.join(30)
    assert [r[0] for r in results] == ["ok"] * 6
    assert sampler.stop() == 1
    assert children(marker) == []


def test_a_newer_request_kills_the_running_one(gate, manager, marker):
    threads, results = in_threads(1, lambda _i: manager.run(sleeper(marker), key="k"))
    assert wait_for(lambda: len(children(marker)) == 1)
    first = children(marker)
    assert manager.run(sleeper(marker, 0.05), key="k") == 0
    threads[0].join(5)
    assert isinstance(results[0][1], offload.SupersededError)
    assert not set(first) & set(children(marker))
    assert children(marker) == []


def test_the_queue_has_a_cap(gate, manager, marker):
    manager.max_queued = 2
    threads, _results = in_threads(3, lambda _i: manager.run(sleeper(marker, 1.0)))
    assert wait_for(lambda: len(manager._waiting) == 2)
    with pytest.raises(KuulasError) as err:
        manager.run(sleeper(marker))
    assert err.value.key == "error.offload.busy"
    manager.shutdown()
    for th in threads:
        th.join(10)
    assert children(marker) == []


def test_cancel_while_waiting_and_while_running(gate, manager, marker):
    running, waiting = threading.Event(), threading.Event()
    threads, results = in_threads(2, lambda i: manager.run(
        sleeper(marker), cancel=(running, waiting)[i]))
    assert wait_for(lambda: len(children(marker)) == 1 and len(manager._waiting) == 1)
    which = 0 if manager._running is not None and manager._running.cancel is running \
        else 1
    (running, waiting)[1 - which].set()  # the one still waiting
    (running, waiting)[which].set()
    for th in threads:
        th.join(5)
    assert all(isinstance(r[1], priority.CancelledError) for r in results)
    assert children(marker) == []


def test_stopped_worker_is_continued_and_killed_when_a_hook_raises(gate, manager,
                                                                   marker):
    def boom():
        raise RuntimeError("hook")

    threads, results = in_threads(1, lambda _i: manager.run(
        sleeper(marker), pause=True, on_pause=boom))
    assert wait_for(lambda: len(children(marker)) == 1)
    gate["playing"] = True
    threads[0].join(5)
    assert isinstance(results[0][1], RuntimeError)
    assert children(marker) == []


def test_wall_clock_timeout_kills_the_worker(gate, marker):
    m = offload.WorkerManager(poll_s=0.01, wall_s=0.3)
    try:
        with pytest.raises(KuulasError) as err:
            m.run(sleeper(marker))
        assert err.value.key == "error.offload.timeout"
    finally:
        m.shutdown()
    assert children(marker) == []


def test_a_failing_key_backs_off_exponentially(gate, marker):
    clock = {"now": 1000.0}
    m = offload.WorkerManager(poll_s=0.01, clock=lambda: clock["now"])
    fail = [sys.executable, "-c", "raise SystemExit(3)", marker]
    try:
        assert m.run(fail, key="curves") == 3
        waits = []
        for _ in range(4):
            with pytest.raises(KuulasError) as err:  # no process: still backing off
                m.run(fail, key="curves")
            assert err.value.key == "error.offload.backoff"
            waits.append(m.backoff_left("curves"))
            clock["now"] += waits[-1] + 0.01
            assert m.run(fail, key="curves") == 3  # the one try after the wait
        assert waits == [5.0, 10.0, 20.0, 40.0]
        assert m.run(sleeper(marker, 0), key="other") == 0  # other keys unaffected
        clock["now"] += 1000
        assert m.run(sleeper(marker, 0), key="curves") == 0
        assert m.backoff_left("curves") == 0  # a success resets it
    finally:
        m.shutdown()
    assert children(marker) == []


def test_a_timeout_backs_off_too(gate, marker):
    m = offload.WorkerManager(poll_s=0.01, wall_s=0.2)
    try:
        with pytest.raises(KuulasError):
            m.run(sleeper(marker), key="curves")
        with pytest.raises(KuulasError) as err:
            m.run(sleeper(marker), key="curves")
        assert err.value.key == "error.offload.backoff"
    finally:
        m.shutdown()
    assert children(marker) == []


def test_watchdog_kills_a_stopped_worker_whose_caller_is_stuck(gate, marker):
    m = offload.WorkerManager(poll_s=0.01, watch_s=0.05, abandon_s=0.5,
                              stop_grace_s=0.2)
    release = threading.Event()
    try:
        threads, _ = in_threads(1, lambda _i: m.run(
            sleeper(marker), pause=True, on_pause=lambda: release.wait(20)))
        assert wait_for(lambda: len(children(marker)) == 1)
        gate["playing"] = True  # the worker is stopped, its caller stuck in the hook
        time.sleep(0.2)
        gate["playing"] = False
        assert wait_for(lambda: children(marker) == [], timeout=5)
        assert m._running is None  # the slot is free again
    finally:
        release.set()
        m.shutdown()
    threads[0].join(5)
    assert children(marker) == []


def test_shutdown_kills_and_reaps_everything(gate, manager, marker):
    gate["playing"] = True
    threads, results = in_threads(3, lambda i: manager.run(
        sleeper(marker), pause=bool(i), key=f"k{i}"))
    assert wait_for(lambda: len(children(marker)) == 1 and len(manager._waiting) == 2)
    manager.shutdown()
    for th in threads:
        th.join(5)
    assert all(isinstance(r[1], priority.CancelledError) for r in results)
    assert children(marker) == []
    with pytest.raises(priority.CancelledError):
        manager.run(sleeper(marker))


def test_closing_a_project_cancels_its_workers(gate, manager, marker):
    threads, results = in_threads(1, lambda _i: manager.run(sleeper(marker),
                                                            owner="/a"))
    assert wait_for(lambda: len(children(marker)) == 1)
    manager.cancel_owner("/b")
    time.sleep(0.1)
    assert len(children(marker)) == 1
    manager.cancel_owner("/a")
    threads[0].join(5)
    assert isinstance(results[0][1], priority.CancelledError)
    assert children(marker) == []


def test_a_foreground_request_preempts_a_stopped_background_worker(gate, manager,
                                                                   marker):
    threads, results = in_threads(1, lambda _i: manager.run(sleeper(marker, 0.3),
                                                            pause=True))
    assert wait_for(lambda: len(children(marker)) == 1)
    gate["playing"] = True
    assert wait_for(lambda: manager._running is not None and manager._running.stopped)
    started = time.monotonic()
    assert manager.run(sleeper(marker, 0.05)) == 0  # does not wait for playback
    assert time.monotonic() - started < 5
    gate["playing"] = False
    threads[0].join(10)
    assert results[0] == ("ok", 0)  # the background request ran again after
    assert children(marker) == []


def test_background_offload_calls_while_playing_pile_up_no_processes(gate, monkeypatch):
    # The bug through the public API: before, each call started its own worker
    # and stopped it; ten calls left ten stopped processes.
    monkeypatch.setattr(offload, "MODE", "process")
    m = offload.WorkerManager(poll_s=0.01)
    monkeypatch.setattr(offload, "MANAGER", m)
    gate["playing"] = True
    cancel = threading.Event()
    threads, _results = in_threads(10, lambda _i: offload.probe(
        {"what": "spin", "seconds": 30}, cancel=cancel, pause=True))
    time.sleep(1.5)
    assert len(children("kuulas.analysis_worker")) <= 1
    cancel.set()
    for th in threads:
        th.join(10)
    m.shutdown()
    assert children("kuulas.analysis_worker") == []


def test_offload_call_uses_one_manager(gate, marker, monkeypatch):
    m = offload.WorkerManager(poll_s=0.01)
    monkeypatch.setattr(offload, "MANAGER", m)
    try:
        info = offload.probe({"what": "priority"}, pause=False)
        assert info["nice"] == offload.WORKER_NICE
    finally:
        m.shutdown()


ORPHAN_PARENT = textwrap.dedent("""
    import os, signal, subprocess, sys
    from kuulas import offload
    proc = subprocess.Popen(sys.argv[1:], **offload.spawn_options())
    os.kill(proc.pid, signal.SIGSTOP)
    print(proc.pid, flush=True)
    os._exit(0)
""")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_a_stopped_worker_dies_with_its_parent(marker):
    # The editor crashes while a worker is stopped: the worker's process group
    # is orphaned, so the kernel sends it SIGHUP and SIGCONT and it ends.
    out = subprocess.run([sys.executable, "-c", ORPHAN_PARENT, *sleeper(marker)],  # noqa: S603
                         capture_output=True, text=True, check=True, timeout=30)
    assert out.stdout.strip()
    assert wait_for(lambda: any_with(marker) == [], timeout=10)


WORKER_PARENT = textwrap.dedent("""
    import pickle, subprocess, sys
    from pathlib import Path
    from kuulas import offload
    tmp = Path(sys.argv[1])
    task = tmp / (sys.argv[2] + ".pickle")  # the marker in the worker's command line
    task.write_bytes(pickle.dumps({"task": "_probe",
                                   "probe": {"what": "spin", "seconds": 60}}))
    argv = offload.worker_argv(task, tmp / "result.pickle")
    proc = subprocess.Popen(argv, start_new_session=True)
    print(proc.pid, flush=True)
""")


def test_a_running_worker_exits_when_its_parent_is_gone(marker, tmp_path):
    # Even in a session of its own (no kernel help), the worker watches its parent.
    env = {**os.environ, "KUULAS_PARENT_CHECK_S": "0.1"}
    out = subprocess.run([sys.executable, "-c", WORKER_PARENT, str(tmp_path), marker],  # noqa: S603
                         capture_output=True, text=True, check=True, timeout=30,
                         env=env)
    pid = int(out.stdout.strip())
    assert wait_for(lambda: any_with(marker) == [], timeout=20), pid


def test_a_worker_exits_when_its_pipe_from_the_editor_closes(tmp_path, marker):
    import pickle  # noqa: PLC0415

    task = tmp_path / f"{marker}.pickle"
    task.write_bytes(pickle.dumps({"task": "_probe",
                                   "probe": {"what": "spin", "seconds": 60}}))
    argv = offload.worker_argv(task, tmp_path / "result.pickle")
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE,  # noqa: S603
                            env={**os.environ, offload.PIPE_ENV: "1"})
    try:
        time.sleep(1.0)
        assert proc.poll() is None  # it runs while the pipe is open
        proc.stdin.close()
        proc.wait(10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    assert proc.returncode != 0


def test_the_manager_gives_its_worker_the_pipe(gate, manager):
    seen = {}

    def popen(argv, **options):
        seen.update(options)
        return subprocess.Popen(argv, **options)  # noqa: S603

    m = offload.WorkerManager(poll_s=0.01, popen=popen)
    try:
        assert m.run([sys.executable, "-c", "pass"]) == 0
    finally:
        m.shutdown()
    assert seen["stdin"] == subprocess.PIPE
    assert seen["env"][offload.PIPE_ENV] == "1"


# -- the startup sweep ---------------------------------------------------------

def test_the_sweep_kills_only_orphaned_analysis_workers():
    me = os.getuid()
    other = me + 1
    listing = "\n".join([
        f"  101     1 {me} /Applications/Kuulas.app/Contents/MacOS/Kuulas -m "
        "kuulas.analysis_worker /tmp/a/task.pickle /tmp/a/result.pickle",
        f"  102   999 {me} /usr/bin/python3 -m kuulas.analysis_worker t r",  # dead parent
        f"  103   500 {me} /usr/bin/python3 -m kuulas.analysis_worker t r",  # live parent
        f"  104     1 {me} /Applications/Kuulas.app/Contents/MacOS/Kuulas -m "
        "kuulas.transcribe_worker run job.json",  # detached on purpose
        f"  105     1 {other} /usr/bin/python3 -m kuulas.analysis_worker t r",  # not ours
        f"  106     1 {me} vim kuulas.analysis_worker.py",  # not a worker
        f"  107     1 {me} /usr/bin/python3 -m kuulas",  # the editor itself
    ])
    sent = []
    killed = offload.sweep_orphans(listing=listing, kill=lambda p, s: sent.append((p, s)),
                                   alive=lambda pid: pid in (1, 500))
    assert killed == [101, 102]
    assert {p for p, _ in sent} == {101, 102}
    assert (101, signal.SIGKILL) in sent


def test_child_processes_are_counted_by_module():
    listing = "\n".join([
        f"  201  {os.getpid()} 501 /Applications/Kuulas.app/Contents/MacOS/Kuulas -m "
        "kuulas.analysis_worker /tmp/a/task.pickle /tmp/a/result.pickle",
        f"  202  {os.getpid()} 501 /usr/bin/python3 -m kuulas.analysis_worker t r",
        f"  203  {os.getpid()} 501 /Applications/Kuulas.app/Contents/MacOS/Kuulas -m "
        "kuulas_recorder serve --socket /tmp/s",
        f"  204  {os.getpid()} 501 /opt/homebrew/bin/ffmpeg -i x.wav -f f32le -",
        "  205     1 501 /usr/bin/python3 -m kuulas.transcribe_worker run j",  # not ours
    ])
    assert offload.child_modules(listing=listing) == {
        "kuulas.analysis_worker": 2, "kuulas_recorder": 1, "ffmpeg": 1}


def test_left_behind_kuulas_processes_are_counted_too():
    listing = "\n".join([
        "  301     1 501 /x/Kuulas -m kuulas.analysis_worker t r",
        "  302     1 501 /x/Kuulas -m kuulas.transcribe_worker run j",
        "  303     1 501 /usr/sbin/cfprefsd agent",  # not kuulas
    ])
    assert offload.orphan_modules(listing=listing, uid=501) == {
        "kuulas.analysis_worker": 1, "kuulas.transcribe_worker": 1}


def test_the_census_is_logged(caplog):
    with caplog.at_level("INFO", logger="kuulas.offload"):
        offload.log_children("start")
    assert any("start" in r.getMessage() for r in caplog.records)


def test_the_sweep_survives_ps_failing(monkeypatch):
    def broken(*_a, **_k):
        raise OSError("no ps")

    monkeypatch.setattr(offload.subprocess, "run", broken)
    assert offload.sweep_orphans() == []
