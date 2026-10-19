"""WP12c: pre-roll in the recorder. While armed the worker listens into a bounded
in-memory buffer and writes nothing; Record writes the buffered seconds first.

Capture tests use ``FakeSource`` driven by the test; protocol tests run the supervisor
with a real worker subprocess on the fake device. No real audio device is opened.
"""

import json
import os
import time

import numpy as np
import pytest
import soundfile as sf
from recorder_helpers import (
    FAKE_ENV,
    RATE,
    FakeAwake,
    FakeDevice,
    contiguous,
    fake_devices,
    ints,
    remove,
    short_dir,
    wait_until,
)

from kuulas_recorder.capture import Capture
from kuulas_recorder.client import RecorderClient, RecorderError
from kuulas_recorder.sources import FakeSource
from kuulas_recorder.supervisor import Supervisor

BLOCK = 1024


class Events(list):
    def __call__(self, ev):
        self.append(ev)

    def of(self, kind):
        return [e for e in self if e["ev"] == kind]


def expected(first: int, n: int, channel: int = 0) -> np.ndarray:
    frames = np.arange(first, first + n, dtype=np.int64)
    return (frames + 1000 * channel) % (1 << 20) - (1 << 19)


def armed(source, preroll_seconds, **kw):
    events = Events()
    c = Capture(source, folder=None, take=None, channels=[1], names=[], rate=RATE,
                blocksize=BLOCK, report=events, armed=True,
                preroll_seconds=preroll_seconds, **kw)
    return c, events


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# -- the capture ---------------------------------------------------------------------


def test_armed_capture_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 1.0)
    c.start()
    src.emit(120)
    assert c.wait_drained()
    c.stop()
    assert list(tmp_path.iterdir()) == []
    assert events.of("opened") == []
    assert events.of("flushed") == []
    assert events.of("listening")  # the supervisor learns the device delivers audio


def test_record_writes_the_buffered_seconds_first(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 1.0)
    c.start()
    src.emit(100)
    assert c.wait_drained()
    c.begin(tmp_path, "t1", ["Olli"])
    src.emit(10)
    c.stop()
    got = ints(tmp_path / "t1-Olli.wav")
    first = 100 * BLOCK - RATE  # exactly one second before Record
    assert np.array_equal(got, expected(first, RATE + 10 * BLOCK))
    assert events.of("preroll") == [{"ev": "preroll", "frames": RATE}]


def test_preroll_is_what_was_heard_when_less_than_asked(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 60.0)
    c.start()
    src.emit(10)
    assert c.wait_drained()
    c.begin(tmp_path, "t1", ["Olli"])
    src.emit(5)
    c.stop()
    assert events.of("preroll")[0]["frames"] == 10 * BLOCK
    assert np.array_equal(ints(tmp_path / "t1-Olli.wav"), expected(0, 15 * BLOCK))


def test_preroll_starts_on_the_recording_clock_before_record(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 1.0)
    c.start()
    src.emit(100)
    assert c.wait_drained()
    c.begin(tmp_path, "t1", ["Olli"])
    src.emit(2)
    c.stop()
    first = events.of("first_block")
    assert len(first) == 1
    ago = time.monotonic_ns() - first[0]["mono_ns"]
    assert 0.9e9 < ago < 3e9  # the take's frame 0 is about a second in the past


def test_no_preroll_when_record_comes_at_once(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 1.0)
    c.start()
    c.begin(tmp_path, "t1", ["Olli"])
    src.emit(5)
    c.stop()
    assert events.of("preroll")[0]["frames"] == 0
    assert len(events.of("first_block")) == 1
    assert np.array_equal(ints(tmp_path / "t1-Olli.wav"), expected(0, 5 * BLOCK))


def test_the_buffer_is_bounded():
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, _events = armed(src, 1.0)
    c.start()
    for _ in range(40):
        src.emit(50)
        assert c.wait_drained()
    assert c.buffered_frames() <= RATE + BLOCK
    c.stop()


def test_levels_are_reported_while_armed():
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 1.0, level_seconds=0.01)
    c.start()
    src.emit(10)
    assert c.wait_drained()
    c.stop()
    assert events.of("levels")


def test_a_file_that_cannot_be_created_ends_the_take_with_an_error(tmp_path):
    src = FakeSource(channels=1, blocksize=BLOCK)
    c, events = armed(src, 1.0)
    c.start()
    src.emit(5)
    assert c.wait_drained()
    (tmp_path / "t1-Olli.wav").write_bytes(b"x")  # never overwritten
    c.begin(tmp_path, "t1", ["Olli"])
    src.emit(1)
    c.stop()
    assert events.of("error")
    assert (tmp_path / "t1-Olli.wav").read_bytes() == b"x"


# -- the protocol ----------------------------------------------------------------------


@pytest.fixture
def fake(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    return dev


@pytest.fixture
def make_sup(tmp_path, fake):
    made = []

    def make(**kw):
        sock_dir = short_dir()
        s = Supervisor(sock_dir / "s.sock", tmp_path / "state",
                       list_devices=fake_devices, disk_free=lambda _p: 100 * 1024**3,
                       keep_awake=FakeAwake(), flush_seconds=0.2, tick=0.05,
                       device_poll=0.2, restart_backoff=0.01, **kw)
        s.open()
        made.append((s, sock_dir))
        return s

    yield make
    for s, sock_dir in made:
        s.close()
        remove(sock_dir)


@pytest.fixture
def sup(make_sup):
    return make_sup()


@pytest.fixture
def client(sup):
    c = RecorderClient.connect(sup.socket_path, timeout=20)
    yield c
    c.close()


def arm(client, preroll_s=1.0, **kw):
    kw.setdefault("channels", [1])
    return client.request("arm", preroll_s=preroll_s, **kw)


def sidecar(folder, take="t1"):
    return json.loads((folder / f"{take}.take.json").read_text())


def test_arm_listens_and_writes_nothing(client, sup, tmp_path):
    folder = tmp_path / "rec"
    answer = arm(client)
    assert answer["state"] == "armed"
    assert answer["armed"]["preroll_s"] == 1.0
    time.sleep(0.5)
    assert not folder.exists()
    assert not (sup.state_dir / "current.json").exists()
    assert [p.name for p in sup.state_dir.iterdir() if p.suffix == ".wav"] == []
    assert client.request("status")["state"] == "armed"
    client.request("disarm")
    assert client.request("status")["state"] == "idle"


def test_record_after_arm_starts_a_second_early(client, tmp_path):
    folder = tmp_path / "rec"
    arm(client, 1.0)
    time.sleep(1.6)  # the buffer is full
    started = client.request("start", folder=str(folder), take="t1", channels=[1],
                             names=["Olli"])
    assert started["state"] == "recording"
    assert started["preroll_frames"] == RATE
    assert started["position_frames"] >= RATE  # the take's clock includes the pre-roll
    time.sleep(0.5)
    client.request("stop")
    side = sidecar(folder)
    assert side["preroll_frames"] == RATE
    assert side["frames"] >= RATE + RATE // 4
    got = ints(folder / "t1-Olli.wav")
    assert contiguous(got)
    assert len(got) == side["frames"]
    assert client.request("status")["state"] == "idle"


def test_start_without_arming_has_no_preroll(client, tmp_path):
    folder = tmp_path / "rec"
    started = client.request("start", folder=str(folder), take="t1", channels=[1],
                             names=["Olli"])
    assert started.get("preroll_frames", 0) == 0
    client.request("stop")
    assert sidecar(folder).get("preroll_frames", 0) == 0


def test_a_short_wait_gives_a_short_preroll(client, tmp_path):
    folder = tmp_path / "rec"
    arm(client, 60.0)
    time.sleep(0.6)
    started = client.request("start", folder=str(folder), take="t1", channels=[1],
                             names=["Olli"])
    client.request("stop")
    assert 0 < started["preroll_frames"] < RATE


def test_arming_again_with_the_same_settings_is_a_keepalive(client):
    first = arm(client)
    again = arm(client)
    assert first["worker_pid"] == again["worker_pid"]


def test_arming_with_other_settings_replaces_the_listener(client):
    first = arm(client, 1.0)
    again = arm(client, 2.0)
    assert again["armed"]["preroll_s"] == 2.0
    assert first["worker_pid"] != again["worker_pid"]


def test_an_armed_recorder_disarms_itself_when_nobody_keeps_it_armed(make_sup):
    s = make_sup(arm_ttl=0.6)
    with RecorderClient.connect(s.socket_path, timeout=20) as c:
        c.request("hello", subscribe=True)
        arm(c)
        ev = c.wait_event("disarmed", timeout=8)
        assert ev["reason"] == "expired"
        assert c.request("status")["state"] == "idle"


def test_disarm_says_so_and_is_harmless_when_idle(client):
    client.request("hello", subscribe=True)
    client.request("disarm")  # idle: nothing to do, not an error
    arm(client)
    client.request("disarm")
    assert client.wait_event("disarmed", timeout=5)["reason"] == "disarmed"


def test_stop_is_not_recording_when_only_armed(client):
    arm(client)
    with pytest.raises(RecorderError) as e:
        client.request("stop")
    assert e.value.key == "not_recording"


def test_arm_is_refused_while_recording(client, tmp_path):
    client.request("start", folder=str(tmp_path / "rec"), take="t1", channels=[1],
                   names=["Olli"])
    with pytest.raises(RecorderError) as e:
        arm(client)
    assert e.value.key == "already_recording"
    client.request("stop")


def test_record_on_other_channels_than_armed_is_refused_and_stays_armed(client, tmp_path):
    arm(client, channels=[1])
    with pytest.raises(RecorderError) as e:
        client.request("start", folder=str(tmp_path / "rec"), take="t1", channels=[2],
                       names=["Olli"])
    assert e.value.key == "armed_mismatch"
    assert client.request("status")["state"] == "armed"


def test_a_take_that_exists_is_refused_and_stays_armed(client, tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    (folder / "t1-Olli.wav").write_bytes(b"x")
    arm(client)
    with pytest.raises(RecorderError) as e:
        client.request("start", folder=str(folder), take="t1", channels=[1],
                       names=["Olli"])
    assert e.value.key == "take_exists"
    assert client.request("status")["state"] == "armed"


def test_a_lost_device_disarms_and_says_so(client, fake):
    client.request("hello", subscribe=True)
    arm(client)
    fake.set(unplugged=True)
    ev = client.wait_event("disarmed", timeout=10)
    assert ev["reason"] == "device_lost"
    assert client.request("status")["state"] == "idle"


def test_arm_needs_a_usable_preroll(client):
    for bad in (0, -1, "60", 100000, True):
        with pytest.raises(RecorderError) as e:
            client.request("arm", preroll_s=bad, channels=[1])
        assert e.value.key == "bad_request"


def test_arm_refuses_a_device_at_the_wrong_rate(client):
    with pytest.raises(RecorderError) as e:
        arm(client, device={"name": "Slow Mic"})
    assert e.value.key == "device_rate_mismatch"
    assert client.request("status")["state"] == "idle"


def test_closing_the_recorder_while_armed_ends_the_listener(make_sup):
    s = make_sup()
    with RecorderClient.connect(s.socket_path, timeout=20) as c:
        arm(c)
        pid = c.request("status")["worker_pid"]
        assert alive(pid)
    s.close()
    wait_until(lambda: not alive(pid), timeout=5)


def test_the_preroll_file_is_a_plain_wav(client, tmp_path):
    folder = tmp_path / "rec"
    arm(client, 1.0)
    time.sleep(1.2)
    client.request("start", folder=str(folder), take="t1", channels=[1], names=["Olli"])
    client.request("stop")
    info = sf.info(folder / "t1-Olli.wav")
    assert (info.channels, info.samplerate, info.subtype) == (1, RATE, "PCM_24")
