"""kuulas_recorder.supervisor: protocol, worker restarts, device loss, disk.

The supervisor runs in this process; its workers are real subprocesses
(``python -m kuulas_recorder worker``) recording from the fake device that
``KUULAS_RECORDER_FAKE`` names. Nothing opens a real audio device.
"""

import json
import os
import signal
import socket
import sys
import textwrap
import threading
import time

import pytest
import soundfile as sf
from recorder_helpers import (
    FAKE_ENV,
    RATE,
    FakeAwake,
    FakeDevice,
    contiguous,
    fake_devices,
    frame_of,
    ints,
    remove,
    short_dir,
    wait_until,
)

from kuulas_recorder import PROTOCOL, supervisor
from kuulas_recorder.client import RecorderClient, RecorderError
from kuulas_recorder.journal import read_journal
from kuulas_recorder.supervisor import RESERVE_BYTES, Supervisor

BPS = RATE * 3  # one channel's bytes a second


@pytest.fixture
def fake(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    return dev


class Disk:
    def __init__(self):
        self.free = 100 * 1024**3

    def __call__(self, _path):
        return self.free


@pytest.fixture
def disk():
    return Disk()


@pytest.fixture
def sup(tmp_path, fake, disk):
    sock_dir = short_dir()
    s = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                   disk_free=disk, keep_awake=FakeAwake(), flush_seconds=0.2,
                   tick=0.05, device_poll=0.2, restart_backoff=0.01)
    s.open()
    yield s
    s.close()
    remove(sock_dir)


@pytest.fixture
def client(sup):
    c = RecorderClient.connect(sup.socket_path, timeout=20)
    yield c
    c.close()


def start(client, folder, take="t1", **kw):
    kw.setdefault("channels", [1])
    kw.setdefault("names", ["Olli"])
    return client.request("start", folder=str(folder), take=take, **kw)


def flushed(sup, frames):
    return wait_until(lambda: sup.status().get("frames_flushed", 0) >= frames)


def sidecar(folder, take="t1"):
    return json.loads((folder / f"{take}.take.json").read_text())


def test_hello_reports_protocol_and_idle_state(client):
    hello = client.request("hello")
    assert hello["protocol"] == PROTOCOL
    assert hello["status"]["state"] == "idle"
    assert client.request("ping")["pong"] is True


def test_errors_carry_a_stable_key_and_a_text(client, sup):
    with pytest.raises(RecorderError) as e:
        client.request("dance")
    assert e.value.key == "unknown_command"
    with pytest.raises(RecorderError) as e:
        client.request("stop")
    assert e.value.key == "not_recording"
    with pytest.raises(RecorderError) as e:
        client.request("start", folder="relative/path", take="t1")
    assert e.value.key == "bad_request"
    with pytest.raises(RecorderError) as e:
        client.request("start", folder="/tmp/x", take="../evil")  # noqa: S108
    assert e.value.key == "bad_name"
    raw = socket.socket(socket.AF_UNIX)
    raw.connect(str(sup.socket_path))
    raw.sendall(b"this is not json\n")
    answer = json.loads(raw.makefile().readline())
    raw.close()
    assert answer["error"]["key"] == "bad_request"
    assert answer["error"]["text"]


def test_devices_come_from_a_fresh_process(tmp_path, fake):
    """The default lister runs ``kuulas-recorder devices --json`` each time, so a
    device plugged in after the recorder started is seen."""
    devs = supervisor.list_devices_subprocess()
    assert [d["name"] for d in devs] == ["Fake Mic", "Slow Mic"]
    fake.set(unplugged=True)
    assert supervisor.list_devices_subprocess() == []


def test_start_records_and_stop_leaves_valid_files(client, sup, tmp_path):
    folder = tmp_path / "recordings"
    st = start(client, folder, channels=[2, 1], names=["Guest", "Host"])
    assert st["state"] == "recording"
    assert sup.keep_awake.active
    flushed(sup, RATE // 2)
    snap = sidecar(folder)  # readable while recording
    assert snap["state"] == "recording"
    assert snap["start_utc"].endswith("Z")
    answer = client.request("stop")
    assert answer["take"]["stop_reason"] == "stopped"
    assert not sup.keep_awake.active
    snap = sidecar(folder)
    assert snap["state"] == "stopped"
    assert snap["device"]["name"] == "Fake Mic"
    assert snap["channels"] == [{"channel": 2, "name": "Guest"},
                                {"channel": 1, "name": "Host"}]
    seg = snap["segments"][0]
    assert seg["start_frame"] == 0
    for name, channel in (("Guest", 1), ("Host", 0)):
        path = folder / seg["files"][name]["file"]
        data = ints(path)
        assert len(data) == seg["files"][name]["frames"] == snap["frames"]
        assert contiguous(data, channel)
    events = [e["event"] for e in read_journal(folder / "t1.journal.jsonl")]
    assert events[0] == "started"
    assert events[-1] == "stopped"
    assert sup.status()["state"] == "idle"
    assert sup.status()["last_take"]["take"] == "t1"


def test_wrong_rate_is_refused_with_the_device_rate(client, tmp_path):
    with pytest.raises(RecorderError) as e:
        start(client, tmp_path / "r", device="Slow Mic")
    assert e.value.key == "device_rate_mismatch"
    assert "44100 Hz" in e.value.text
    assert not (tmp_path / "r").exists() or not list((tmp_path / "r").iterdir())


def test_missing_channel_is_refused(client, tmp_path):
    with pytest.raises(RecorderError) as e:
        start(client, tmp_path / "r", channels=[3])
    assert e.value.key == "channels_unavailable"


def test_a_device_that_fails_to_open_leaves_no_files(client, sup, tmp_path):
    """The device list said yes, the worker could not open it."""
    sup.list_devices = lambda: [{"index": 7, "name": "Ghost", "channels": 1,
                                 "default_rate": 48000.0, "hostapi": "fake",
                                 "default": True}]
    with pytest.raises(RecorderError) as e:
        start(client, tmp_path / "r")
    assert e.value.key == "device_not_found"
    assert list((tmp_path / "r").iterdir()) == []
    assert sup.status()["state"] == "idle"


def test_an_existing_take_is_never_overwritten(client, sup, tmp_path):
    folder = tmp_path / "r"
    folder.mkdir()
    (folder / "t1-Olli.wav").write_bytes(b"older")
    with pytest.raises(RecorderError) as e:
        start(client, folder)
    assert e.value.key == "take_exists"
    assert (folder / "t1-Olli.wav").read_bytes() == b"older"


def test_second_start_is_refused_while_recording(client, sup, tmp_path):
    start(client, tmp_path / "r")
    with pytest.raises(RecorderError) as e:
        start(client, tmp_path / "r", take="t2")
    assert e.value.key == "already_recording"
    with pytest.raises(RecorderError) as e:
        client.request("quit")
    assert e.value.key == "busy"
    client.request("stop")


def test_subscribers_get_started_level_and_stopped(client, sup, tmp_path):
    client.request("subscribe", levels=True)
    start(client, tmp_path / "r")
    assert client.wait_event("started")["take"] == "t1"
    level = client.wait_event("level")
    assert len(level["peak_dbfs"]) == 1
    assert -40 < level["peak_dbfs"][0] <= -24  # the counter peaks at 1/16: -24 dBFS
    client.request("stop")
    assert client.wait_event("stopped")["stop_reason"] == "stopped"


def test_levels_returns_the_peak_since_the_last_call(client, sup, tmp_path):
    start(client, tmp_path / "r")
    flushed(sup, RATE // 4)
    first = client.request("levels")
    assert first["names"] == ["Olli"]
    assert first["peak_dbfs"][0] > -40
    assert first["clipped"] == [False]
    client.request("stop")


def test_mark_lands_in_the_journal_and_the_sidecar(client, sup, tmp_path):
    folder = tmp_path / "r"
    start(client, folder)
    flushed(sup, RATE // 4)
    mark = client.request("mark", text="good bit")
    assert mark["at_frame"] > 0
    client.request("stop")
    snap = sidecar(folder)
    assert snap["markers"][0]["text"] == "good bit"
    journal = read_journal(folder / "t1.journal.jsonl")
    assert any(e["event"] == "mark" and e["text"] == "good bit" for e in journal)


def test_closing_the_client_does_not_stop_the_recording(sup, tmp_path):
    folder = tmp_path / "r"
    with RecorderClient.connect(sup.socket_path) as first:
        start(first, folder)
    # The editor quit (or crashed). The take goes on.
    before = flushed(sup, RATE // 4)
    flushed(sup, before + RATE // 4)
    with RecorderClient.connect(sup.socket_path) as again:
        status = again.request("hello")["status"]
        assert status["state"] == "recording"
        assert status["take"] == "t1"
        assert status["position_frames"] > 0
        again.request("stop")
    assert sidecar(folder)["state"] == "stopped"


def test_a_client_that_stops_reading_is_dropped_and_recording_goes_on(
        sup, client, tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "CLIENT_QUEUE", 8)
    monkeypatch.setattr(supervisor, "CLIENT_SEND_TIMEOUT", 0.2)
    start(client, tmp_path / "r")
    stuck = socket.socket(socket.AF_UNIX)
    stuck.connect(str(sup.socket_path))
    stuck.setblocking(False)
    payload = b'{"cmd": "ping"}\n' * 200
    sent = 0
    t_end = time.monotonic() + 5
    while time.monotonic() < t_end:  # flood it; never read an answer
        try:
            sent += stuck.send(payload)
        except BlockingIOError:
            time.sleep(0.01)
        except OSError:
            break  # the supervisor gave up on us
        if sent > 2_000_000:
            break
    a = sup.status()["frames_flushed"]
    flushed(sup, a + RATE // 4)  # recording went on meanwhile
    assert client.request("ping")["pong"]
    wait_until(lambda: len(sup.clients) == 1, timeout=10)
    stuck.close()
    client.request("stop")


def test_killing_the_worker_restarts_into_a_new_numbered_file(client, sup, tmp_path):
    folder = tmp_path / "r"
    client.request("subscribe")
    start(client, folder)
    flushed(sup, RATE // 2)
    os.kill(sup.status()["worker_pid"], signal.SIGKILL)
    restarted = client.wait_event("worker_restarted")
    assert restarted["restarts"] == 1
    gap = client.wait_event("gap")
    assert gap["reason"] == "worker_restart"
    assert gap["frames"] > 0
    st = flushed(sup, sup.status()["frames_flushed"] + RATE // 4)
    assert st
    client.request("stop")
    snap = sidecar(folder)
    assert snap["worker_restarts"] == 1
    assert snap["gaps"][0]["reason"] == "worker_restart"
    one, two = snap["segments"]
    assert (one["segment"], two["segment"]) == (1, 2)
    assert two["files"]["Olli"]["file"] == "t1-Olli~2.wav"
    assert two["start_frame"] == one["start_frame"] + one["files"]["Olli"]["frames"] + (
        snap["gaps"][0]["frames"])
    p1, p2 = folder / "t1-Olli.wav", folder / "t1-Olli~2.wav"
    assert contiguous(ints(p1))
    assert contiguous(ints(p2))
    # The fake source and the supervisor timestamp in separate processes. Allow
    # 200 ms for process scheduling jitter while still catching misplaced segments.
    real = (frame_of(p2) - frame_of(p1)) % (1 << 20)
    assert abs(real - two["start_frame"]) < RATE // 5
    journal = [e["event"] for e in read_journal(folder / "t1.journal.jsonl")]
    assert "worker_restarted" in journal
    assert "gap" in journal


def test_device_unplug_and_return_continue_the_take(client, sup, fake, tmp_path):
    folder = tmp_path / "r"
    client.request("subscribe")
    start(client, folder)
    flushed(sup, RATE // 2)
    fake.set(unplugged=True)
    lost = client.wait_event("device_lost")
    assert lost["device"]["name"] == "Fake Mic"
    assert sup.status()["state"] == "device_lost"
    time.sleep(0.5)
    fake.set(unplugged=False)
    assert client.wait_event("device_back")["device"]["name"] == "Fake Mic"
    gap = client.wait_event("gap")
    assert gap["reason"] == "device_lost"
    assert gap["frames"] >= RATE // 2  # it was gone at least half a second
    flushed(sup, sup.status()["frames_flushed"] + RATE // 4)
    client.request("stop")
    snap = sidecar(folder)
    assert len(snap["segments"]) == 2
    assert snap["worker_restarts"] == 0
    events = [e["event"] for e in read_journal(folder / "t1.journal.jsonl")]
    assert events.index("device_lost") < events.index("device_back") < events.index(
        "gap")
    for seg in snap["segments"]:
        assert sf.info(folder / seg["files"]["Olli"]["file"]).frames > 0


def test_stop_while_the_device_is_gone_ends_the_take(client, sup, fake, tmp_path):
    folder = tmp_path / "r"
    client.request("subscribe")
    start(client, folder)
    flushed(sup, RATE // 4)
    fake.set(unplugged=True)
    client.wait_event("device_lost")
    client.request("stop")
    assert sidecar(folder)["state"] == "stopped"
    assert sf.info(folder / "t1-Olli.wav").frames > 0


def test_disk_warnings_then_a_graceful_stop_before_it_is_full(client, sup, disk,
                                                               tmp_path):
    folder = tmp_path / "r"
    client.request("subscribe")
    start(client, folder)
    flushed(sup, RATE // 4)
    disk.free = RESERVE_BYTES + BPS * 500  # under 10 minutes left
    warning = client.wait_event("warning")
    assert warning["key"] == "disk_low"
    assert 400 < warning["seconds_left"] <= 500
    disk.free = RESERVE_BYTES + BPS * 5
    error = client.wait_event("error")
    assert error["key"] == "disk_full"
    stopped = client.wait_event("stopped")
    assert stopped["stop_reason"] == "disk_full"
    snap = sidecar(folder)
    assert snap["state"] == "stopped"
    data = ints(folder / "t1-Olli.wav")
    assert len(data) == snap["frames"] > 0
    assert contiguous(data)


def test_start_is_refused_when_the_disk_is_full(client, disk, tmp_path):
    disk.free = RESERVE_BYTES + BPS * 30
    with pytest.raises(RecorderError) as e:
        start(client, tmp_path / "r")
    assert e.value.key == "disk_full"


def test_start_warns_when_little_space_is_left(client, disk, tmp_path):
    disk.free = RESERVE_BYTES + BPS * 900
    st = start(client, tmp_path / "r")
    assert st["warning"]["key"] == "disk_low"
    client.request("stop")


def fake_worker(tmp_path, body: str) -> list[str]:
    """A stand-in worker script: speaks the worker's stdout protocol."""
    script = tmp_path / "fake_worker.py"
    script.write_text(textwrap.dedent("""
        import json, sys, time
        cfg = json.loads(sys.stdin.readline())
        seg = cfg["segment"]
        folder, take, name = cfg["folder"], cfg["take"], cfg["names"][0]
        def say(**ev):
            print(json.dumps(ev), flush=True)
        def wav(seg):
            import struct
            f = f"{take}-{name}.wav" if seg == 1 else f"{take}-{name}~{seg}.wav"
            open(folder + "/" + f, "wb").write(struct.pack(
                "<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + 300, b"WAVE", b"fmt ", 16, 1, 1,
                48000, 144000, 3, 24, b"data", 300) + bytes(300))
            say(ev="opened", segment=seg, continues=False, files={name: f})
            say(ev="first_block", segment=seg, mono_ns=time.monotonic_ns(),
                utc_ns=time.time_ns())
            say(ev="flushed", segment=seg, frames={name: 100}, overflows=0)
    """) + textwrap.dedent(body))
    return [sys.executable, str(script)]


def test_a_full_disk_in_the_worker_ends_the_take(tmp_path, fake, disk):
    sock_dir = short_dir()
    argv = fake_worker(tmp_path, """
        wav(seg)
        say(ev="error", key="disk_full", text="No space left on device")
        sys.exit(3)
    """)
    s = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                   disk_free=disk, keep_awake=FakeAwake(), worker_argv=argv)
    s.open()
    try:
        with RecorderClient.connect(s.socket_path) as c:
            c.request("subscribe")
            start(c, tmp_path / "r")
            assert c.wait_event("error")["key"] == "disk_full"
            assert c.wait_event("stopped")["stop_reason"] == "disk_full"
        assert s.status()["state"] == "idle"
    finally:
        s.close()
        remove(sock_dir)


def test_a_worker_that_keeps_dying_is_not_restarted_forever(tmp_path, fake, disk):
    sock_dir = short_dir()
    argv = fake_worker(tmp_path, """
        if seg == 1:
            wav(seg)
            time.sleep(0.3)
        sys.exit(1)
    """)
    s = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                   disk_free=disk, keep_awake=FakeAwake(), worker_argv=argv, tick=0.02,
                   restart_backoff=0.005)
    s.open()
    try:
        with RecorderClient.connect(s.socket_path) as c:
            c.request("subscribe")
            start(c, tmp_path / "r")
            assert c.wait_event("error", timeout=20)["key"] == "worker_keeps_failing"
            assert c.wait_event("stopped")["stop_reason"] == "worker_keeps_failing"
        snap = sidecar(tmp_path / "r")
        assert snap["worker_restarts"] == supervisor.RESTART_LIMIT
        assert snap["state"] == "stopped"
        assert len(snap["segments"]) == 1  # the empty restarts left nothing behind
    finally:
        s.close()
        remove(sock_dir)


def test_only_one_supervisor_runs_per_state_folder(sup, tmp_path):
    other = Supervisor(sup.socket_path, sup.state_dir, list_devices=fake_devices,
                       keep_awake=FakeAwake())
    with pytest.raises(supervisor.ProtocolError) as e:
        other.open()
    assert e.value.key == "already_running"


def test_repair_command_rebuilds_an_interrupted_take(client, sup, tmp_path):
    folder = tmp_path / "r"
    start(client, folder)
    flushed(sup, RATE // 4)
    client.request("stop")
    snap = sidecar(folder)
    snap["state"] = "recording"  # as a crash would have left it
    (folder / "t1.take.json").write_text(json.dumps(snap))
    with open(folder / "t1-Olli.wav", "ab") as f:
        f.write(b"\x00\x00\x01\x00")  # a frame and a bit after the last flush
    result = client.request("repair", folder=str(folder), take="t1")
    assert result["state"] == "interrupted"
    assert result["frames"] == snap["frames"] + 1
    assert sf.info(folder / "t1-Olli.wav").frames == snap["frames"] + 1


def test_a_device_that_sends_no_audio_is_refused_at_start(client, sup, fake, tmp_path):
    fake.set(stall=True)
    with pytest.raises(RecorderError) as e:
        start(client, tmp_path / "r")
    assert e.value.key == "device_no_audio"
    assert "Fake Mic" in e.value.text
    assert list((tmp_path / "r").iterdir()) == []
    assert sup.status()["state"] == "idle"
    assert not sup.keep_awake.active


def test_an_idle_client_stays_connected(sup, monkeypatch):
    """The send timeout that drops a stuck client must not drop a quiet one."""
    monkeypatch.setattr(supervisor, "CLIENT_SEND_TIMEOUT", 0.2)
    with RecorderClient.connect(sup.socket_path) as c:
        for _ in range(3):
            assert c.request("ping")["pong"]
            time.sleep(0.6)  # the editor has nothing to say for a while


def test_quit_reply_is_sent_before_an_immediate_shutdown(client, sup, monkeypatch):
    """The main thread may wake and close sockets as soon as shutdown is requested.
    Force that interleaving instead of hoping the race happens on this machine.
    """
    wait_until(lambda: bool(sup.clients))
    request_shutdown = sup.request_shutdown

    def close_immediately():
        request_shutdown()
        sup.close()

    monkeypatch.setattr(sup, "request_shutdown", close_immediately)
    assert client.request("quit", timeout=2) == {"id": 1, "ok": True, "quitting": True}
    assert sup.shutdown_requested.wait(2)


def test_quit_still_shuts_down_if_its_reply_cannot_be_delivered(client, sup, monkeypatch):
    client.request("ping")
    wait_until(lambda: bool(sup.clients))
    server_client = next(iter(sup.clients))

    def broken_send(_data, **_kwargs):
        raise BrokenPipeError

    monkeypatch.setattr(server_client.conn, "send", broken_send)
    with pytest.raises(RecorderError) as error:
        client.request("quit", timeout=2)
    assert error.value.key == "disconnected"
    assert sup.shutdown_requested.wait(2)


def test_two_closes_at_once_release_the_lock_file_only_once(sup, monkeypatch):
    """The socket's thread closes the supervisor right after a quit while the main
    thread (or a test's teardown) closes it too: the second call must wait for the first
    and find nothing left to do, not close the lock file's descriptor again (EBADF)."""
    entered = threading.Event()
    release = threading.Event()
    stop_awake = sup.keep_awake.stop

    def slow_stop():
        entered.set()
        release.wait(5)
        stop_awake()

    monkeypatch.setattr(sup.keep_awake, "stop", slow_stop)
    lock_fd = sup._lock_fd
    closed_fds = []
    real_close = os.close

    def counting_close(fd):
        closed_fds.append(fd)
        real_close(fd)

    monkeypatch.setattr(supervisor.os, "close", counting_close)
    errors = []

    def close():
        try:
            sup.close()
        except OSError as e:  # the bug: EBADF from a second os.close
            errors.append(e)

    first = threading.Thread(target=close)
    first.start()
    assert entered.wait(2)
    second = threading.Thread(target=close)
    second.start()
    time.sleep(0.2)  # the second one is either waiting for the first or past it
    release.set()
    first.join(5)
    second.join(5)
    assert not errors
    assert closed_fds.count(lock_fd) == 1
