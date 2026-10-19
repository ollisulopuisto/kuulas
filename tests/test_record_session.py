"""record_session: the editor's side of recording (WP12a part B).

Two kinds of test: with a scripted fake client (errors, a recorder that is missing or
dies), and end to end with a real recorder supervisor in this process recording from
the fake device (``KUULAS_RECORDER_FAKE``, docs/RECORDER.md). No audio device opens.
"""

import json
import threading
import time

import numpy as np
import pytest
import soundfile as sf
from recorder_helpers import (
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
from kuulas_recorder.sources import FAKE_ENV
from kuulas_recorder.supervisor import Supervisor

RATE = 48000


# -- helpers ------------------------------------------------------------------------


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


def offline(session, **kw):
    """A RecordSession whose recorder never answers and cannot be started."""
    return RecordSession(session, Published(), connect=nobody, spawn=no_spawn,
                         watch=False, **kw)


def write_take(folder, take="Take 1", state="stopped", segments=((0, RATE),), plan=None):
    """A take as the recorder leaves it: WAVs (24-bit mono) and the snapshot."""
    folder.mkdir(parents=True, exist_ok=True)
    segs = []
    for n, (start, frames) in enumerate(segments, 1):
        name = f"{take}-Olli.wav" if n == 1 else f"{take}-Olli~{n}.wav"
        sf.write(folder / name, np.full(frames, 0.1, dtype=np.float32), RATE,
                 subtype="PCM_24")
        segs.append({"segment": n, "start_frame": start, "start_flicks": 0,
                     "files": {"Olli": {"file": name, "frames": frames}}})
    data = {"format": 1, "take": take, "state": state, "rate": RATE,
            "channels": [{"channel": 1, "name": "Olli"}], "segments": segs,
            "frames": sum(f for _, f in segments), "gaps": [], "dropouts": [],
            "overflows": 0, "worker_restarts": 0}
    (folder / f"{take}.take.json").write_text(json.dumps(data))
    if plan is not None:
        rt.write_plan(folder, plan)
    return data


def recordings(session):
    return session.package.path / "recordings"


# -- importing a take (no recorder needed) ---------------------------------------------


def test_a_take_becomes_one_clip_per_segment_in_one_undo_step(session):
    folder = recordings(session)
    write_take(folder, segments=((0, RATE), (RATE + 4800, RATE // 2)),
               plan=rt.TakePlan("Take 1", at=96000, track_id=None, track_name="Olli",
                                channel=1))
    rs = offline(session)
    head = session.history.head
    result = rs.import_take("Take 1")
    p = session.state
    assert result["clips"] == 2
    track = p.tracks[-1]
    assert (track.name, track.kind, track.mono) == ("Olli", "speech", True)
    assert [(c.start, c.length) for c in track.clips] == [(96000, RATE),
                                                         (96000 + RATE + 4800, RATE // 2)]
    assert {c.name for c in track.clips} == {"Take 1"}
    assert len(p.sync_groups) == 1  # the gap is real time: the segments stay together
    # one step: one undo takes all of it away
    session.undo()
    assert session.history.head == head
    assert not session.state.tracks


def test_take_files_are_linked_in_place_never_copied(session):
    folder = recordings(session)
    write_take(folder, plan=rt.TakePlan("Take 1", 0, None, "Olli", 1))
    offline(session).import_take("Take 1")
    media = session.state.media[0]
    meta = session.store.meta(media.id)
    assert meta["storage"] == "linked"
    assert meta["linked_package_rel"] == "recordings/Take 1-Olli.wav"


def test_onto_an_existing_track_trims_what_lies_under(session):
    folder = recordings(session)
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    write_take(folder, plan=rt.TakePlan("Take 1", 0, "t1", "Host", 1))
    offline(session).import_take("Take 1")
    assert [t.id for t in session.state.tracks] == ["t1"]
    assert len(session.state.tracks[0].clips) == 1


def test_a_take_is_imported_once(session):
    folder = recordings(session)
    write_take(folder, plan=rt.TakePlan("Take 1", 0, None, "Olli", 1))
    rs = offline(session)
    assert rs.import_take("Take 1") is not None
    assert rs.import_take("Take 1") is None
    # a fresh editor (a restart) sees it in the project too
    assert offline(session).import_take("Take 1") is None
    assert offline(session).pending() == []


def test_an_interrupted_take_says_so_in_its_name(session):
    write_take(recordings(session), state="interrupted",
               plan=rt.TakePlan("Take 1", 0, None, "Olli", 1))
    result = offline(session).import_take("Take 1")
    assert result["interrupted"] is True
    assert session.state.tracks[0].clips[0].name == "Take 1 (interrupted)"


def test_a_take_without_a_plan_goes_to_a_new_track_at_the_start(session):
    write_take(recordings(session))
    offline(session).import_take("Take 1")
    track = session.state.tracks[0]
    assert track.name == "Take 1"
    assert track.clips[0].start == 0


def test_takes_never_imported_are_offered_not_imported(tmp_path):
    folder = tmp_path / "Show.kuulas" / "recordings"
    s = Session(tmp_path / "Show.kuulas")
    try:
        write_take(folder, "Take 1")
        write_take(folder, "Take 2", state="recording")
        rs = offline(s)
        offered = rs.pending()
        assert [(p["take"], p["readiness"]) for p in offered] == [
            ("Take 1", "import"), ("Take 2", "repair")]
        assert not s.state.tracks  # nothing came in by itself
    finally:
        s.close()


def test_a_crashed_take_is_repaired_by_the_recorder_before_import(session):
    write_take(recordings(session), state="recording",
               plan=rt.TakePlan("Take 1", 0, None, "Olli", 1))
    asked = []

    class Repairing:
        closed = False

        def request(self, cmd, timeout=None, **args):
            asked.append(cmd)
            if cmd == "status":
                return {"state": "idle"}
            if cmd == "repair":
                path = recordings(session) / "Take 1.take.json"
                data = json.loads(path.read_text())
                data["state"] = "interrupted"
                path.write_text(json.dumps(data))
                return {"state": "interrupted"}
            raise AssertionError(cmd)

        def close(self):
            pass

    rs = RecordSession(session, Published(), connect=Repairing, spawn=no_spawn,
                       watch=False)
    result = rs.import_take("Take 1")
    assert "repair" in asked
    assert result["interrupted"] is True


def test_a_crashed_take_imports_as_it_is_when_no_recorder_can_repair_it(session):
    write_take(recordings(session), state="recording")
    result = offline(session).import_take("Take 1")
    assert result["clips"] == 1
    assert result["interrupted"] is True


# -- failures with no recorder ---------------------------------------------------------


def test_no_recorder_is_a_clear_error_key(session):
    rs = offline(session)
    with pytest.raises(RecordError) as e:
        rs.devices()
    assert e.value.key == "error.record.unavailable"
    assert e.value.status == 503


def test_status_without_a_recorder_says_unavailable_and_never_starts_one(session):
    spawned = []
    rs = RecordSession(session, Published(), connect=nobody,
                       spawn=lambda: spawned.append(1), watch=False)
    status = rs.status()
    assert status["available"] is False
    assert status["recording"] is False
    assert spawned == []


def test_start_spawns_the_recorder_when_nobody_answers(session):
    spawned = []
    rs = RecordSession(session, Published(), connect=nobody,
                       spawn=lambda: spawned.append(1), watch=False)
    with pytest.raises(RecordError) as e:
        rs.start(device=None, channel=1, track_id=None, name="Olli", at=0)
    assert spawned == [1]
    assert e.value.key == "error.record.unavailable"
    # a failed start leaves no plan behind
    assert not list(recordings(session).glob("*.editor.json"))


@pytest.mark.parametrize(("mode", "held"), [(None, 0), ("hold", 500), ("swipe", 9999)])
def test_stop_without_a_deliberate_gesture_is_refused(session, mode, held):
    with pytest.raises(RecordError) as e:
        offline(session).stop(mode, held)
    assert e.value.key in ("error.record.hold_required", "error.record.stop_gesture")


def test_a_read_only_project_cannot_record(session, monkeypatch):
    monkeypatch.setattr(type(session), "read_only", property(lambda _s: True))
    with pytest.raises(Exception) as e:  # noqa: PT011 - the key is what matters
        offline(session).start(device=None, channel=1, track_id=None, name="", at=0)
    assert e.value.key == "error.history.read_only"


def test_the_recorder_dying_mid_take_is_an_alarm_and_a_new_recorder_is_started(session):
    published = Published()
    spawned = threading.Event()
    folder = str(recordings(session))

    class Dying:
        def __init__(self):
            self.closed = False
            self.events = [{"event": "level", "peak_dbfs": [-20.0], "clipped": [False],
                            "position_frames": 4800}]

        def request(self, cmd, timeout=None, **args):
            if cmd == "hello":
                return {"status": {"state": "recording", "take": "Take 1",
                                   "folder": folder}}
            return {"state": "idle"}

        def next_event(self, timeout=None):
            if self.events:
                return self.events.pop(0)
            self.closed = True
            return None

        def close(self):
            pass

    calls = []

    def connect():
        calls.append(1)
        if len(calls) == 1:
            return Dying()
        raise ConnectionRefusedError

    rs = RecordSession(session, published, connect=connect, spawn=spawned.set,
                       retry_s=0.05)
    try:
        assert spawned.wait(5)
        assert published.kinds("level")[0]["position_frames"] == 4800
        alarms = [m for m in published.kinds("notice")
                  if m["key"] == "record.event.recorder_lost"]
        assert alarms
        assert alarms[0]["level"] == "alarm"
    finally:
        rs.close()


# -- end to end with a recorder on the fake device -------------------------------------


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    dev = FakeDevice(tmp_path / "fake.json")
    monkeypatch.setenv(FAKE_ENV, str(dev.path))
    sock_dir = short_dir()
    sup = Supervisor(sock_dir / "s.sock", tmp_path / "state", list_devices=fake_devices,
                     disk_free=lambda _p: 100 * 1024**3, keep_awake=FakeAwake(),
                     flush_seconds=0.2, tick=0.05, device_poll=0.2, restart_backoff=0.01)
    sup.open()
    sup.fake = dev
    yield sup
    sup.close()
    remove(sock_dir)


def live(session, recorder, published=None):
    return RecordSession(
        session, published if published is not None else Published(),
        connect=lambda: RecorderClient.connect(recorder.socket_path, timeout=20),
        spawn=no_spawn, retry_s=0.1)


def test_devices_come_from_the_recorder(session, recorder):
    rs = live(session, recorder)
    try:
        names = [d["name"] for d in rs.devices()]
        assert names == ["Fake Mic", "Slow Mic"]
    finally:
        rs.close()


def test_record_a_take_and_it_lands_where_it_was_recorded(session, recorder):
    published = Published()
    rs = live(session, recorder, published)
    try:
        view = rs.start(device={"index": 0, "name": "Fake Mic"}, channel=1,
                        track_id=None, name="Olli", at=48000)
        assert view["recording"]
        assert view["ours"]
        assert view["take"] == "Take 1"
        wait_until(lambda: published.kinds("level"), timeout=10)
        time.sleep(0.6)
        result = rs.stop("two_step")
        assert result["imported"]["clips"] == 1
        track = session.state.tracks[0]
        assert track.name == "Olli"
        clip = track.clips[0]
        assert clip.start == 48000
        assert clip.length > RATE // 4
        assert (recordings(session) / "Take 1-Olli.wav").exists()
        assert published.kinds("imported")
        assert rs.pending() == []
    finally:
        rs.close()


def test_wrong_rate_device_is_refused_with_a_key(session, recorder):
    rs = live(session, recorder)
    try:
        with pytest.raises(RecordError) as e:
            rs.start(device={"index": 1, "name": "Slow Mic"}, channel=1, track_id=None,
                     name="Olli", at=0)
        assert e.value.key == "error.record.device_rate_mismatch"
        assert e.value.params["rate"] == 48000
        assert not list(recordings(session).glob("*.editor.json"))
    finally:
        rs.close()


def test_closing_the_editor_does_not_stop_the_recording(session, recorder):
    first = live(session, recorder)
    first.start(device=None, channel=1, track_id=None, name="Olli", at=9600)
    first.close()
    time.sleep(0.4)
    with RecorderClient.connect(recorder.socket_path) as c:
        assert c.request("status")["state"] == "recording"
    # a reopened editor finds it, shows it and can stop it; the plan says where it goes
    second = live(session, recorder)
    try:
        status = second.status()
        assert status["recording"]
        assert status["ours"]
        assert status["plan"]["at"] == 9600
        second.stop("one_click")
        assert session.state.tracks[0].clips[0].start == 9600
    finally:
        second.close()


def test_another_projects_take_is_shown_but_not_ours(session, recorder, tmp_path):
    other = Session(tmp_path / "Other.kuulas")
    a = live(other, recorder)
    b = live(session, recorder)
    try:
        a.start(device=None, channel=1, track_id=None, name="Olli", at=0)
        status = b.status()
        assert status["recording"]
        assert not status["ours"]
        assert status["elsewhere"]
        with pytest.raises(RecordError) as e:
            b.stop("two_step")
        assert e.value.key == "error.record.another_project"
        with pytest.raises(RecordError) as e:
            b.start(device=None, channel=1, track_id=None, name="Olli", at=0)
        assert e.value.key == "error.record.already_recording"
        a.stop("two_step")
    finally:
        a.close()
        b.close()
        other.close()


def test_a_device_unplug_is_a_notice_and_the_take_goes_on(session, recorder):
    published = Published()
    rs = live(session, recorder, published)
    try:
        rs.start(device=None, channel=1, track_id=None, name="Olli", at=0)
        wait_until(lambda: published.kinds("level"), timeout=10)
        recorder.fake.set(unplugged=True)
        wait_until(lambda: [m for m in published.kinds("notice")
                            if m["key"] == "record.event.device_lost"], timeout=10)
        assert rs.status()["recording"]
        recorder.fake.set(unplugged=False)
        wait_until(lambda: [m for m in published.kinds("notice")
                            if m["key"] == "record.event.device_back"], timeout=10)
        # the notices of the take are kept for a page that opens now
        assert any(n["key"] == "record.event.device_lost"
                   for n in rs.status()["notices"])
        wait_until(lambda: [m for m in published.kinds("notice")
                            if m["key"] == "record.event.gap"], timeout=10)
        time.sleep(0.4)
        result = rs.stop("two_step")
        assert result["imported"]["clips"] == 2  # before and after the gap
    finally:
        rs.close()


# -- the HTTP API ----------------------------------------------------------------------


class NoEngine:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1

    def status(self):
        return {"playing": False, "position": 0, "notices": []}


def api(session, tmp_path, recorder=None, engine=None):
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from kuulas.server import create_app  # noqa: PLC0415

    ui = tmp_path / "ui"
    ui.mkdir(exist_ok=True)
    return TestClient(create_app(session, engine or NoEngine(), language="en", ui_dir=ui,
                                 recorder=recorder))


def test_api_without_a_recorder_says_unavailable_and_edits_on(session, tmp_path):
    with api(session, tmp_path) as c:
        assert c.get("/api/record/status").json()["available"] is False
        r = c.get("/api/record/devices")
        assert r.status_code == 503
        assert r.json()["error"]["key"] == "error.record.unavailable"
        r = c.post("/api/edit", json={"op": "add_track", "args": {}})
        assert r.status_code == 200


def test_api_refuses_a_stop_without_a_gesture(session, tmp_path):
    rs = offline(session)
    with api(session, tmp_path, rs) as c:
        r = c.post("/api/record/stop", json={})
        assert r.status_code == 400
        assert r.json()["error"]["key"] == "error.record.stop_gesture"
        r = c.post("/api/record/stop", json={"mode": "hold", "held_ms": 1999})
        assert r.json()["error"]["key"] == "error.record.hold_required"


def test_api_imports_an_offered_take_on_one_click(session, tmp_path):
    write_take(recordings(session), plan=rt.TakePlan("Take 1", 4800, None, "Olli", 1))
    rs = offline(session)
    with api(session, tmp_path, rs) as c:
        status = c.get("/api/record/status").json()
        assert [p["take"] for p in status["pending"]] == ["Take 1"]
        assert not session.state.tracks  # offered, not imported
        r = c.post("/api/record/import", json={"takes": ["Take 1"]})
        assert r.status_code == 200
        body = r.json()
        assert body["imported"][0]["clips"] == 1
        assert body["pending"] == []
        assert body["project"]["tracks"][0]["clips"][0]["start"] == 4800


def test_api_records_end_to_end_and_stops_playback_first(session, tmp_path, recorder):
    engine = NoEngine()
    rs = live(session, recorder)
    try:
        with api(session, tmp_path, rs, engine) as c:
            r = c.post("/api/record/start", json={
                "device": {"index": 0, "name": "Fake Mic"}, "channel": 2,
                "track_id": "new", "name": "Guest", "at": 0})
            assert r.status_code == 200, r.text
            assert engine.stops == 1
            assert r.json()["recording"]
            time.sleep(0.8)
            r = c.post("/api/record/stop", json={"mode": "two_step"})
            assert r.status_code == 200, r.text
            tracks = r.json()["project"]["tracks"]
            assert tracks[0]["name"] == "Guest"
            assert tracks[0]["clips"]
    finally:
        rs.close()
