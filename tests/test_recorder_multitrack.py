"""WP12b through the supervisor: two channels of the fake device in one take, and a
channel that fails mid-take (docs/RECORDER.md, "Several channels")."""

import json

import pytest
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

from kuulas_recorder.client import RecorderClient
from kuulas_recorder.journal import read_journal
from kuulas_recorder.supervisor import Supervisor


@pytest.fixture
def sup(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    sock_dir = short_dir()
    s = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                   disk_free=lambda _p: 100 * 1024**3, keep_awake=FakeAwake(),
                   flush_seconds=0.2, tick=0.05, device_poll=0.2, restart_backoff=0.01)
    s.open()
    yield s
    s.close()
    remove(sock_dir)


@pytest.fixture
def client(sup):
    c = RecorderClient.connect(sup.socket_path, timeout=20)
    yield c
    c.close()


def sidecar(folder, take="t1"):
    return json.loads((folder / f"{take}.take.json").read_text())


def test_two_channels_land_in_two_files_in_sync(client, sup, tmp_path):
    folder = tmp_path / "r"
    client.request("start", folder=str(folder), take="t1", channels=[1, 2],
                   names=["Host", "Guest"])
    wait_until(lambda: sup.status().get("frames_flushed", 0) >= RATE // 2)
    client.request("stop")
    snap = sidecar(folder)
    assert [c["name"] for c in snap["channels"]] == ["Host", "Guest"]
    host, guest = ints(folder / "t1-Host.wav"), ints(folder / "t1-Guest.wav")
    assert len(host) == len(guest) == snap["frames"]
    assert contiguous(host, 0)
    assert contiguous(guest, 1)


def test_a_failed_channel_is_recorded_and_the_other_goes_on(client, sup, tmp_path):
    folder = tmp_path / "r"
    client.request("start", folder=str(folder), take="t1", channels=[1, 2],
                   names=["Host", "Guest"])
    wait_until(lambda: sup.status().get("frames_flushed", 0) >= RATE // 4)
    client.request("subscribe", events=True)
    sup.on_worker_event(sup.worker, {"ev": "channel_failed", "segment": 1,
                                     "name": "Guest", "at": 1000,
                                     "text": "Guest: Input/output error"})
    warning = client.wait_event("warning")
    assert (warning["key"], warning["name"]) == ("channel_failed", "Guest")
    client.request("stop")
    snap = sidecar(folder)
    assert snap["failed_channels"] == [{"name": "Guest", "at_frame": 1000,
                                        "text": "Guest: Input/output error"}]
    assert any(line["event"] == "channel_failed"
               for line in read_journal(folder / "t1.journal.jsonl"))
