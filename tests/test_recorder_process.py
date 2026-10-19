"""The recorder as real processes: SIGTERM, SIGKILL of everything, recovery.

``kuulas-recorder serve`` runs as its own session (as the editor starts it),
records from the fake device, and is then signalled or killed outright.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys

import pytest
import soundfile as sf
from recorder_helpers import (
    FAKE_ENV,
    RATE,
    FakeDevice,
    contiguous,
    ints,
    remove,
    short_dir,
    wait_until,
)

from kuulas_recorder.client import RecorderClient, spawn_supervisor
from kuulas_recorder.journal import read_journal
from kuulas_recorder.wavfile import repair_wav, wav_frames


@pytest.fixture
def env(tmp_path):
    dev = FakeDevice(tmp_path / "fake.json")
    e = os.environ.copy()
    e[FAKE_ENV] = str(dev.path)
    return e


@pytest.fixture
def sock():
    d = short_dir()
    yield d / "s.sock"
    remove(d)


def spawn(sock, tmp_path, env):
    return spawn_supervisor(sock, state_dir=tmp_path / "state", env=env,
                            extra=["--flush-seconds", "0.2"])


def frames_flushed(c) -> int:
    return c.request("status").get("frames_flushed", 0)


def kill_group(proc):
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(10)


def test_sigterm_flushes_and_closes_the_take(tmp_path, env, sock):
    folder = tmp_path / "r"
    proc = spawn(sock, tmp_path, env)
    try:
        with RecorderClient.connect(sock) as c:
            c.request("start", folder=str(folder), take="t1", channels=[1],
                      names=["Olli"])
            wait_until(lambda: frames_flushed(c) > RATE // 2)
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(20) == 0
    finally:
        kill_group(proc)
    snap = json.loads((folder / "t1.take.json").read_text())
    assert (snap["state"], snap["stop_reason"]) == ("stopped", "shutdown")
    data = ints(folder / "t1-Olli.wav")
    assert len(data) == snap["frames"] > RATE // 2
    assert contiguous(data)
    assert not sock.exists()


def test_sigint_is_a_clean_stop_too(tmp_path, env, sock):
    folder = tmp_path / "r"
    proc = spawn(sock, tmp_path, env)
    try:
        with RecorderClient.connect(sock) as c:
            c.request("start", folder=str(folder), take="t1", channels=[1],
                      names=["Olli"])
            wait_until(lambda: frames_flushed(c) > RATE // 4)
        # Ctrl+C in a terminal reaches the whole group; the worker ignores it and
        # the supervisor stops the take.
        os.killpg(proc.pid, signal.SIGINT)
        assert proc.wait(20) == 0
    finally:
        kill_group(proc)
    assert json.loads((folder / "t1.take.json").read_text())["stop_reason"] == "shutdown"


def test_sigkill_of_the_whole_recorder_leaves_readable_files(tmp_path, env, sock):
    """Supervisor and worker killed at once, mid-take, with no warning: every
    file opens as it is, with everything up to the last flush, and the next
    recorder start repairs the take and reports it."""
    folder = tmp_path / "r"
    proc = spawn(sock, tmp_path, env)
    try:
        with RecorderClient.connect(sock) as c:
            c.request("start", folder=str(folder), take="t1", channels=[1, 2],
                      names=["A", "B"])
            seen = wait_until(lambda: frames_flushed(c) > RATE)
            worker = c.request("status")["worker_pid"]
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(10)
        wait_until(lambda: not _alive(worker))
    finally:
        kill_group(proc)
    for ch, name in enumerate(["A", "B"]):
        path = folder / f"t1-{name}.wav"
        info = sf.info(path)  # opens without any repair
        assert info.frames >= seen
        data = ints(path)
        assert contiguous(data, ch)
        assert repair_wav(path).frames >= info.frames
    snap = json.loads((folder / "t1.take.json").read_text())
    assert snap["state"] == "recording"  # nobody had the chance to close it

    proc = spawn(sock, tmp_path, env)
    try:
        with RecorderClient.connect(sock) as c:
            status = c.request("hello")["status"]
        recovered = status["recovered"][0]
        assert recovered["take"] == "t1"
        assert recovered["state"] == "interrupted"
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(20)
        kill_group(proc)
    snap = json.loads((folder / "t1.take.json").read_text())
    assert (snap["state"], snap["stop_reason"]) == ("interrupted", "recorder_crashed")
    assert snap["frames"] == wav_frames(folder / "t1-A.wav")
    assert read_journal(folder / "t1.journal.jsonl")[-1]["event"] == "recovered"


def test_supervisor_killed_alone_lets_the_worker_close_its_files(tmp_path, env, sock):
    """With the supervisor gone nobody could stop the worker, so it stops itself
    (its stdin closes) and leaves closed, complete files."""
    folder = tmp_path / "r"
    proc = spawn(sock, tmp_path, env)
    try:
        with RecorderClient.connect(sock) as c:
            c.request("start", folder=str(folder), take="t1", channels=[1],
                      names=["Olli"])
            wait_until(lambda: frames_flushed(c) > RATE // 4)
            worker = c.request("status")["worker_pid"]
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(10)
        wait_until(lambda: not _alive(worker), timeout=10)
    finally:
        kill_group(proc)
    path = folder / "t1-Olli.wav"
    before = path.read_bytes()
    assert not repair_wav(path).changed  # the worker's final flush covered it all
    assert path.read_bytes() == before


def test_the_console_script_answers(tmp_path, env):
    out = subprocess.run([sys.executable, "-m", "kuulas_recorder", "devices"],
                         capture_output=True, text=True, env=env, check=True)
    assert "Fake Mic" in out.stdout


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie (dead, not yet reaped by its killed parent) counts as gone.
    st = subprocess.run(  # noqa: S603 - fixed argv
        ["ps", "-o", "stat=", "-p", str(pid)],  # noqa: S607 - the system ps
        capture_output=True, text=True, check=False).stdout.strip()
    return bool(st) and not st.startswith("Z")

