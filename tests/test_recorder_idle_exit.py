"""The recorder does not run forever: idle with nobody connected, it exits by itself;
it never does while a take records, while armed, or while an editor is connected."""

import time

import pytest
from recorder_helpers import (
    FAKE_ENV,
    FakeAwake,
    FakeDevice,
    fake_devices,
    remove,
    short_dir,
    wait_until,
)

from kuulas_recorder import PROTOCOL
from kuulas_recorder.client import RecorderClient
from kuulas_recorder.supervisor import IDLE_EXIT_S, Supervisor

LINGER = 0.4


@pytest.fixture
def sup(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    sock_dir = short_dir()
    s = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                   disk_free=lambda _p: 100 * 1024**3, keep_awake=FakeAwake(),
                   flush_seconds=0.2, tick=0.05, device_poll=0.2, restart_backoff=0.01,
                   idle_exit=LINGER)
    s.open()
    yield s
    s.close()
    remove(sock_dir)


def connect(sup):
    return RecorderClient.connect(sup.socket_path, timeout=20)


def test_the_default_is_a_minute():
    assert IDLE_EXIT_S == 60


def test_hello_reports_the_protocol_the_editor_checks():
    assert PROTOCOL >= 2


def test_idle_with_no_editor_it_exits_by_itself(sup):
    wait_until(sup.shutdown_requested.is_set, timeout=5)


def test_a_connected_editor_keeps_it_alive_and_leaving_starts_the_clock(sup):
    c = connect(sup)
    time.sleep(LINGER * 3)
    assert not sup.shutdown_requested.is_set()
    c.close()
    wait_until(sup.shutdown_requested.is_set, timeout=5)


def test_a_connection_inside_the_window_resets_it(sup):
    time.sleep(LINGER * 0.6)
    c = connect(sup)
    time.sleep(LINGER * 2)
    assert not sup.shutdown_requested.is_set()
    c.close()


def test_it_stays_while_listening_for_pre_roll(sup):
    c = connect(sup)
    c.request("arm", preroll_s=30, channels=[1])
    wait_until(lambda: sup.status()["state"] == "armed", timeout=10)
    c.close()
    time.sleep(LINGER * 3)
    assert not sup.shutdown_requested.is_set()  # armed until its own time-to-live


def test_it_never_exits_with_a_take_running_even_with_nobody_connected(sup, tmp_path):
    c = connect(sup)
    c.request("start", folder=str(tmp_path / "r"), take="t1", channels=[1],
              names=["Olli"])
    wait_until(lambda: sup.status().get("frames_flushed", 0) > 0, timeout=10)
    c.close()
    time.sleep(LINGER * 4)
    assert not sup.shutdown_requested.is_set()
    assert sup.status()["state"] == "recording"
    c = connect(sup)
    c.request("stop")
    c.close()
    wait_until(sup.shutdown_requested.is_set, timeout=5)  # idle again: the clock runs


def test_the_last_editor_quitting_while_idle_ends_it_at_once(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    sock_dir = short_dir()
    s = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                   keep_awake=FakeAwake(), tick=0.05, idle_exit=3600)
    s.open()
    try:
        c = connect(s)
        c.request("quit")
        wait_until(s.shutdown_requested.is_set, timeout=2)
    finally:
        s.close()
        remove(sock_dir)
