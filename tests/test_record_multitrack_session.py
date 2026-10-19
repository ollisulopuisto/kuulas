"""Recording several channels at once through the editor's side (WP12b): the fake
device has two channels; nothing opens a real audio device."""

import json
import time

import numpy as np
import pytest
import soundfile as sf
from recorder_helpers import (
    FAKE_ENV,
    FakeAwake,
    FakeDevice,
    fake_devices,
    remove,
    short_dir,
    wait_until,
)

from kuulas import record_take as rt
from kuulas.record_session import RecordError, RecordSession
from kuulas.session import Session
from kuulas_recorder.client import RecorderClient, RecorderError
from kuulas_recorder.supervisor import Supervisor

RATE = 48000
DEVICE = {"index": 0, "name": "Fake Mic"}


def nobody():
    raise ConnectionRefusedError("no recorder")


def no_spawn():
    raise RecorderError("spawn_failed", "The recorder exited at once (code 1).")


class Published(list):
    def __call__(self, message):
        self.append(message)

    def kinds(self, kind):
        return [m for m in self if m.get("kind") == kind]


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Show.kuulas")
    yield s
    s.close()


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    sock_dir = short_dir()
    sup = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                     disk_free=lambda _p: 100 * 1024**3, keep_awake=FakeAwake(),
                     flush_seconds=0.2, tick=0.05, device_poll=0.2, restart_backoff=0.01)
    sup.open()
    yield sup
    sup.close()
    remove(sock_dir)


def live(session, recorder, published=None):
    return RecordSession(
        session, published if published is not None else Published(),
        connect=lambda: RecorderClient.connect(recorder.socket_path, timeout=20),
        spawn=no_spawn, retry_s=0.1)


def offline(session):
    return RecordSession(session, Published(), connect=nobody, spawn=no_spawn,
                         watch=False)


def recordings(session):
    return session.package.path / "recordings"


def lane(channel, track_id=None, name=""):
    return {"channel": channel, "track_id": track_id, "name": name}


def write_two_channel_take(folder, take="Take 1", failed=False, plan=None):
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    channels = (("Host", RATE), ("Guest", 0 if failed else RATE))
    for level, (name, frames) in enumerate(channels):
        wav = f"{take}-{name}.wav"
        # Different content per channel: media is identified by its hash.
        sf.write(folder / wav, np.full(frames, 0.1 * (level + 1), dtype=np.float32),
                 RATE, subtype="PCM_24")
        files[name] = {"file": wav, "frames": frames}
    data = {"format": 1, "take": take, "state": "stopped", "rate": RATE,
            "channels": [{"channel": 1, "name": "Host"}, {"channel": 2, "name": "Guest"}],
            "segments": [{"segment": 1, "start_frame": 0, "start_flicks": 0,
                          "files": files}],
            "frames": RATE, "gaps": [], "dropouts": [], "overflows": 0,
            "worker_restarts": 0, "preroll_frames": 0,
            "failed_channels": [{"name": "Guest", "at_frame": 0, "text": "x"}]
            if failed else []}
    (folder / f"{take}.take.json").write_text(json.dumps(data))
    if plan is not None:
        rt.write_plan(folder, plan)


def two_lane_plan(guest_track=None):
    lanes = (rt.Lane(1, "Host", None, "Host"), rt.Lane(2, "Guest", guest_track, "Guest"))
    return rt.TakePlan("Take 1", at=RATE, track_id=None, track_name="Host", channel=1,
                       lanes=lanes)


# -- importing (no recorder) ---------------------------------------------------------


def test_two_channels_become_two_tracks_in_one_undo_step_and_one_sync_group(session):
    write_two_channel_take(recordings(session), plan=two_lane_plan())
    head = session.history.head
    result = offline(session).import_take("Take 1")
    p = session.state
    assert result["clips"] == 2
    assert [t.name for t in p.tracks] == ["Host", "Guest"]
    assert all(t.mono and t.kind == "speech" for t in p.tracks)
    assert [t.clips[0].start for t in p.tracks] == [RATE, RATE]
    assert len(p.sync_groups) == 1
    assert len(p.sync_groups[0].members) == 2
    session.undo()  # one step takes both tracks away
    assert session.history.head == head
    assert not session.state.tracks


def test_a_channel_can_go_onto_an_existing_track(session):
    session.edit("add_track", {"track_id": "t1", "name": "Guest mic"})
    write_two_channel_take(recordings(session), plan=two_lane_plan(guest_track="t1"))
    offline(session).import_take("Take 1")
    p = session.state
    assert [t.name for t in p.tracks] == ["Guest mic", "Host"]
    assert len(p.tracks[0].clips) == len(p.tracks[1].clips) == 1


def test_a_channel_that_failed_before_any_audio_makes_no_empty_track(session):
    write_two_channel_take(recordings(session), failed=True, plan=two_lane_plan())
    result = offline(session).import_take("Take 1")
    assert result["failed_channels"] == ["Guest"]
    assert result["clips"] == 1
    assert [t.name for t in session.state.tracks] == ["Host"]


def test_every_file_of_a_two_channel_take_is_linked_in_place(session):
    write_two_channel_take(recordings(session), plan=two_lane_plan())
    offline(session).import_take("Take 1")
    rels = {session.store.meta(m.id)["linked_package_rel"] for m in session.state.media}
    assert rels == {"recordings/Take 1-Host.wav", "recordings/Take 1-Guest.wav"}


def test_a_take_without_a_plan_still_imports_its_first_channel(session):
    write_two_channel_take(recordings(session))
    offline(session).import_take("Take 1")
    assert len(session.state.tracks) == 1


# -- asking (before the recorder is reached) -------------------------------------------


@pytest.mark.parametrize("lanes", [
    [],
    [lane(0)],
    [lane(1), lane(1)],
    [lane("1")],
])
def test_nonsense_channels_are_refused_with_a_key(session, lanes):
    with pytest.raises(RecordError) as e:
        offline(session).start(device=DEVICE, channels=lanes, at=0)
    assert e.value.key == "error.record.bad_channel"


def test_two_channels_on_one_existing_track_are_refused(session):
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    with pytest.raises(RecordError) as e:
        offline(session).start(device=DEVICE, at=0,
                               channels=[lane(1, "t1"), lane(2, "t1")])
    assert e.value.key == "error.record.same_track"


# -- end to end on the fake device ---------------------------------------------------


def test_record_two_channels_onto_two_tracks(session, recorder):
    session.edit("add_track", {"track_id": "t1", "name": "Guest mic"})
    published = Published()
    rs = live(session, recorder, published)
    try:
        view = rs.start(device=DEVICE, at=RATE,
                        channels=[lane(2, "t1"), lane(1, None, "Host")])
        assert view["recording"]
        assert [lane_["channel"] for lane_ in view["plan"]["lanes"]] == [1, 2]
        wait_until(lambda: published.kinds("level"), timeout=10)
        # every channel is metered
        assert len(published.kinds("level")[-1]["peak_dbfs"]) == 2
        time.sleep(0.6)
        result = rs.stop("two_step")
        assert result["imported"]["clips"] == 2
        p = session.state
        by_name = {t.name: t for t in p.tracks}
        assert set(by_name) == {"Guest mic", "Host"}
        host, guest = by_name["Host"].clips[0], by_name["Guest mic"].clips[0]
        assert host.start == guest.start == RATE
        assert abs(host.length - guest.length) < RATE // 8
        assert (recordings(session) / "Take 1-Host.wav").exists()
        assert (recordings(session) / "Take 1-Guest mic.wav").exists()
        assert rs.pending() == []
    finally:
        rs.close()


def test_blank_new_tracks_are_named_after_their_channel(session, recorder):
    rs = live(session, recorder)
    try:
        rs.start(device=DEVICE, at=0, channels=[lane(1), lane(2)])
        time.sleep(0.4)
        rs.stop("one_click")
        assert [t.name for t in session.state.tracks] == ["Channel 1", "Channel 2"]
    finally:
        rs.close()


def test_pre_roll_works_with_several_channels(session, recorder):
    rs = live(session, recorder)
    try:
        view = rs.arm(device=DEVICE, channels=[2, 1], preroll_s=1.0)
        assert view["armed"]
        time.sleep(1.3)
        rs.start(device=DEVICE, at=3 * RATE,
                 channels=[lane(2, None, "B"), lane(1, None, "A")])
        time.sleep(0.4)
        rs.stop("one_click")
        tracks = {t.name: t for t in session.state.tracks}
        a, b = tracks["A"].clips[0], tracks["B"].clips[0]
        assert a.start == b.start == 3 * RATE - RATE
        assert abs(a.length - b.length) < RATE // 8
    finally:
        rs.close()


def test_a_channel_that_fails_mid_take_keeps_the_others_and_says_so(session, recorder):
    published = Published()
    rs = live(session, recorder, published)
    try:
        rs.start(device=DEVICE, at=0,
                 channels=[lane(1, None, "Host"), lane(2, None, "Guest")])
        wait_until(lambda: recorder.status().get("frames_flushed", 0) >= RATE // 4)
        recorder.on_worker_event(recorder.worker, {
            "ev": "channel_failed", "segment": 1, "name": "Guest", "at": 100,
            "text": "Guest: Input/output error"})
        wait_until(lambda: any(n["key"] == "record.event.channel_failed"
                               for n in published.kinds("notice")))
        result = rs.stop("one_click")
        assert result["imported"]["failed_channels"] == ["Guest"]
        assert {t.name for t in session.state.tracks} == {"Host", "Guest"}
    finally:
        rs.close()
