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

from kuulas import clipboard_level
from kuulas import record_session as record_session_module
from kuulas import record_take as rt
from kuulas.ops import EditError
from kuulas.record_session import RecordError, RecordSession, default_connect
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


def test_watcher_is_not_started_when_unix_sockets_are_unavailable(session, monkeypatch):
    monkeypatch.setattr(record_session_module, "socket", object(), raising=False)
    with pytest.raises(OSError, match=r"^$"):
        default_connect()
    rs = RecordSession(session)
    try:
        assert rs._thread is None
        assert not rs._available
    finally:
        rs.close()


def write_take(folder, take="Take 1", state="stopped", segments=((0, RATE),), plan=None,
               preroll=0):
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
            "overflows": 0, "worker_restarts": 0, "preroll_frames": preroll}
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


def test_a_take_says_how_much_existing_audio_it_replaced(session):
    folder = recordings(session)
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    write_take(folder, "Old", plan=rt.TakePlan("Old", 0, "t1", "Host", 1))
    rs = offline(session)
    assert rs.import_take("Old")["replaced"] == []  # nothing was under it
    # A second take, half a second later, covers the last half of the first.
    write_take(folder, "New", plan=rt.TakePlan("New", RATE // 2, "t1", "Host", 1))
    result = rs.import_take("New")
    assert result["replaced"] == [{"track": "Host", "frames": RATE // 2}]


def test_a_take_over_a_whole_older_clip_replaces_all_of_it(session):
    folder = recordings(session)
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    write_take(folder, "Old", plan=rt.TakePlan("Old", RATE, "t1", "Host", 1))
    rs = offline(session)
    rs.import_take("Old")
    write_take(folder, "New", plan=rt.TakePlan("New", 0, "t1", "Host", 1),
               segments=((0, 3 * RATE),))
    assert rs.import_take("New")["replaced"] == [{"track": "Host", "frames": RATE}]


def test_a_take_is_imported_once(session):
    folder = recordings(session)
    write_take(folder, plan=rt.TakePlan("Take 1", 0, None, "Olli", 1))
    rs = offline(session)
    first = rs.import_take("Take 1")
    assert first is not None
    # The stop answer and the stopped event both import; whichever comes second gets the
    # same result, not None (found as a flaky test: the stop answer had no clips).
    assert rs.import_take("Take 1") == first
    assert len(session.state.tracks) == 1
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


def test_a_project_opened_by_a_relative_path_records_into_an_absolute_folder(
        tmp_path, monkeypatch):
    # Found in the browser: `kuulas open Try.kuulas` sent "recordings" relative, and the
    # recorder refused it ("start needs an absolute folder path").
    monkeypatch.chdir(tmp_path)
    s = Session("Rel.kuulas")
    try:
        rs = offline(s)
        assert rs.folder.is_absolute()
        assert rs.folder == (tmp_path / "Rel.kuulas" / "recordings").resolve()
    finally:
        s.close()


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


def test_api_plays_nothing_while_a_take_records(session, tmp_path):
    # Owner, 2026-10-19: no listening while recording in this version.
    rs = offline(session)
    rs._status = {"state": "recording", "take": "Take 1",
                  "folder": str(recordings(session))}
    with api(session, tmp_path, rs) as c:
        r = c.post("/api/transport", json={"action": "play", "at": 0})
        assert r.status_code == 409
        assert r.json()["error"]["key"] == "error.record.no_playback"
        rs._status = {"state": "idle"}
        r = c.post("/api/transport", json={"action": "stop"})
        assert r.status_code == 200


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


# -- pre-roll (WP12c) -------------------------------------------------------------------


def test_a_take_with_preroll_starts_before_where_record_was_pressed(session):
    folder = recordings(session)
    write_take(folder, segments=((0, RATE),), preroll=RATE // 2,
               plan=rt.TakePlan("Take 1", at=96000, track_id=None, track_name="Olli",
                                channel=1))
    offline(session).import_take("Take 1")
    clip = session.state.tracks[0].clips[0]
    assert (clip.start, clip.offset, clip.length) == (96000 - RATE // 2, 0, RATE)


def test_preroll_before_the_timeline_start_is_trimmed_and_undoable(session):
    folder = recordings(session)
    write_take(folder, segments=((0, RATE),), preroll=RATE // 2,
               plan=rt.TakePlan("Take 1", at=RATE // 10, track_id=None,
                                track_name="Olli", channel=1))
    head = session.history.head
    offline(session).import_take("Take 1")
    clip = session.state.tracks[0].clips[0]
    assert clip.start == 0
    assert clip.offset == RATE // 2 - RATE // 10
    assert clip.length == RATE - clip.offset
    session.undo()
    assert session.history.head == head


def test_arming_listens_without_recording_and_a_take_includes_the_preroll(
        session, recorder):
    published = Published()
    rs = live(session, recorder, published)
    try:
        view = rs.arm(device={"index": 0, "name": "Fake Mic"}, channel=1, preroll_s=1.0)
        assert view["armed"]
        assert view["preroll_s"] == 1.0
        assert not view["recording"]
        assert not rs.recording_now()  # listening does not block playback
        wait_until(lambda: published.kinds("level"), timeout=10)  # meters while armed
        assert not recordings(session).exists() or not list(recordings(session).iterdir())
        time.sleep(1.3)
        rs.start(device={"index": 0, "name": "Fake Mic"}, channel=1, track_id=None,
                 name="Olli", at=3 * RATE)
        time.sleep(0.4)
        result = rs.stop("two_step")
        assert result["imported"]["clips"] == 1
        clip = session.state.tracks[0].clips[0]
        assert clip.start == 3 * RATE - RATE  # one second before Record
        assert clip.length > RATE + RATE // 8
    finally:
        rs.close()


def test_a_take_started_near_the_timeline_start_is_trimmed(session, recorder):
    rs = live(session, recorder)
    try:
        rs.arm(device=None, channel=1, preroll_s=1.0)
        time.sleep(1.3)
        rs.start(device=None, channel=1, track_id=None, name="Olli", at=RATE // 4)
        time.sleep(0.3)
        rs.stop("one_click")
        clip = session.state.tracks[0].clips[0]
        assert (clip.start, clip.offset) == (0, RATE - RATE // 4)
    finally:
        rs.close()


def test_disarm_lets_the_microphone_go(session, recorder):
    rs = live(session, recorder)
    try:
        rs.arm(device=None, channel=1, preroll_s=1.0)
        assert rs.disarm()["armed"] is False
        with RecorderClient.connect(recorder.socket_path) as c:
            assert c.request("status")["state"] == "idle"
    finally:
        rs.close()


def test_closing_the_editor_while_armed_disarms(session, recorder):
    rs = live(session, recorder)
    rs.arm(device=None, channel=1, preroll_s=1.0)
    rs.close()
    with RecorderClient.connect(recorder.socket_path) as c:
        assert c.request("status")["state"] == "idle"


def test_closing_the_editor_does_not_disarm_what_it_never_armed(session, recorder):
    with RecorderClient.connect(recorder.socket_path) as c:
        c.request("arm", preroll_s=1.0, channels=[1])
        rs = live(session, recorder)
        rs.close()
        assert c.request("status")["state"] == "armed"


def test_arming_without_a_recorder_is_a_key(session):
    with pytest.raises(RecordError) as e:
        offline(session).arm(device=None, channel=1, preroll_s=1.0)
    assert e.value.key == "error.record.unavailable"


def test_arming_with_nonsense_is_refused_before_asking_the_recorder(session):
    rs = offline(session)
    for bad in (0, -5, 100000):
        with pytest.raises(RecordError) as e:
            rs.arm(device=None, channel=1, preroll_s=bad)
        assert e.value.key == "error.record.bad_request"
    with pytest.raises(RecordError) as e:
        rs.arm(device=None, channel=0, preroll_s=10)
    assert e.value.key == "error.record.bad_channel"


def test_api_arms_and_disarms(session, tmp_path, recorder):
    rs = live(session, recorder)
    try:
        with api(session, tmp_path, rs) as c:
            r = c.post("/api/record/arm", json={
                "device": {"index": 0, "name": "Fake Mic"}, "channel": 1,
                "preroll_s": 30})
            assert r.status_code == 200, r.text
            assert r.json()["armed"] is True
            assert c.get("/api/record/status").json()["armed"] is True
            r = c.post("/api/record/disarm", json={})
            assert r.status_code == 200
            assert r.json()["armed"] is False
    finally:
        rs.close()


def test_api_records_several_channels_onto_several_tracks(session, tmp_path, recorder):
    rs = live(session, recorder)
    try:
        with api(session, tmp_path, rs) as c:
            r = c.post("/api/record/arm", json={
                "device": {"index": 0, "name": "Fake Mic"}, "channels": [1, 2],
                "preroll_s": 30})
            assert r.status_code == 200, r.text
            r = c.post("/api/record/start", json={
                "device": {"index": 0, "name": "Fake Mic"}, "at": 0,
                "channels": [{"channel": 1, "track_id": "new", "name": "Host"},
                             {"channel": 2, "track_id": "new", "name": "Guest"}]})
            assert r.status_code == 200, r.text
            assert [lane["track_name"] for lane in r.json()["plan"]["lanes"]] == [
                "Host", "Guest"]
            time.sleep(0.6)
            r = c.post("/api/record/stop", json={"mode": "one_click"})
            assert r.status_code == 200, r.text
            assert [t["name"] for t in r.json()["project"]["tracks"]] == ["Host", "Guest"]
            r = c.post("/api/record/start", json={"channels": [{"channel": 0}]})
            assert r.status_code == 400
    finally:
        rs.close()


# -- editing is paused while a take of this project records (owner, 2026-10-23) ---------


def recording_status(rs, folder=None):
    rs._status = {"state": "recording", "take": "Take 1",
                  "folder": str(rs.folder if folder is None else folder)}


def test_edits_are_paused_while_a_take_of_this_project_records(session):
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    rs = offline(session)
    recording_status(rs)
    with pytest.raises(EditError) as e:
        session.edit("set_track", {"track_id": "t1", "gain_db": -3.0})
    assert e.value.key == "error.edit.recording_paused"
    with pytest.raises(EditError):
        session.undo()
    assert session.state.tracks[0].gain_db == 0.0


def test_markers_may_still_be_added_and_moved_while_recording(session):
    rs = offline(session)
    recording_status(rs)
    session.edit("add_marker", {"marker_id": "k1", "name": "Good answer", "start": 4800})
    session.edit("move_marker", {"marker_id": "k1", "start": 9600})
    assert [m.start for m in session.state.markers] == [9600]


def test_a_take_still_lands_while_the_recorder_says_recording(session):
    # The stop answer and the stopped event both import; the status may lag behind.
    folder = recordings(session)
    write_take(folder, plan=rt.TakePlan("Take 1", 0, None, "Olli", 1))
    rs = offline(session)
    recording_status(rs)
    assert rs.import_take("Take 1")["clips"] == 1


def test_edits_work_again_when_the_take_is_over(session):
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    rs = offline(session)
    recording_status(rs)
    rs._status = {"state": "idle"}
    session.edit("set_track", {"track_id": "t1", "gain_db": -3.0})
    assert session.state.tracks[0].gain_db == -3.0


def test_a_take_of_another_project_does_not_pause_this_one(session, tmp_path):
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    rs = offline(session)
    recording_status(rs, folder=tmp_path / "Other.kuulas" / "recordings")
    session.edit("set_track", {"track_id": "t1", "gain_db": -3.0})
    assert session.state.tracks[0].gain_db == -3.0


def test_listening_for_pre_roll_does_not_pause_edits(session):
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    rs = offline(session)
    rs._status = {"state": "armed", "folder": str(rs.folder)}
    session.edit("set_track", {"track_id": "t1", "gain_db": -3.0})
    assert session.state.tracks[0].gain_db == -3.0


# -- a new track exists from the moment the take starts (so it can be drawn live) ------


def started(rs, take_key="take"):
    """A RecordSession whose recorder answers `start` as recording (no process)."""
    def command(cmd, **kw):
        return {"state": "recording", "take": kw.get("take", "Take 1"),
                "folder": str(rs.folder), "position_frames": 0}
    rs._command = command
    return rs


def test_a_new_track_is_made_when_the_take_starts_and_the_plan_names_it(session):
    rs = started(offline(session))
    rs.start(device=None, at=0, channels=[
        {"channel": 1, "track_id": None, "name": "Olli"},
        {"channel": 2, "track_id": None, "name": "Anna"}])
    names = [tr.name for tr in session.state.tracks]
    assert names == ["Olli", "Anna"]
    assert all(tr.mono and tr.kind == "speech" for tr in session.state.tracks)
    plans = [p for p in rs.folder.iterdir() if p.name.endswith(rt.PLAN_SUFFIX)]
    plan = rt.read_plan(rs.folder, plans[0].name[:-len(rt.PLAN_SUFFIX)])
    made = [tr.id for tr in session.state.tracks]
    assert [lane.track_id for lane in plan.all_lanes] == made


def test_the_tracks_of_a_take_are_one_undo_step(session):
    rs = started(offline(session))
    head = session.history.head
    rs.start(device=None, at=0, channels=[
        {"channel": 1, "track_id": None, "name": "Olli"}])
    assert len(session.state.tracks) == 1
    rs._status = {"state": "idle"}
    session.undo()
    assert session.history.head == head
    assert not session.state.tracks


def test_a_take_on_an_existing_track_makes_no_track(session):
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    rs = started(offline(session))
    rs.start(device=None, at=0, channels=[{"channel": 1, "track_id": "t1", "name": ""}])
    assert [tr.id for tr in session.state.tracks] == ["t1"]


def test_the_take_lands_on_the_track_made_at_the_start(session):
    rs = started(offline(session))
    rs.start(device=None, at=96000, channels=[
        {"channel": 1, "track_id": None, "name": "Olli"}])
    made = session.state.tracks[0].id
    plans = [p for p in rs.folder.iterdir() if p.name.endswith(rt.PLAN_SUFFIX)]
    take = plans[0].name[:-len(rt.PLAN_SUFFIX)]
    write_take(rs.folder, take, plan=rt.read_plan(rs.folder, take))
    rs._status = {"state": "idle"}
    rs.import_take(take)
    assert [tr.id for tr in session.state.tracks] == [made]  # no second track
    assert len(session.state.tracks[0].clips) == 1


# -- the cart while recording: a played clip is put on the timeline where it was played --


def test_a_clip_played_during_a_take_lands_on_the_cart_track_at_that_moment(session):
    rs = started(offline(session))
    session.edit("add_track", {"track_id": "tq", "name": "Questions"})
    rs.start(device=None, at=48000, cart_track="tq",
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    path = recordings(session).parent / "q.wav"
    sf.write(path, np.full(RATE * 2, 0.1, dtype=np.float32), RATE, subtype="PCM_16")
    report = session.store.import_batch([str(path)], copy=False)
    entry_id = session.material_copy(report[0].media.id)["entry"]["id"]
    rs._position = 2 * RATE  # two seconds into the take
    result = rs.cart_log(entry_id)
    assert result["at"] == 48000 + 2 * RATE
    track = next(tr for tr in session.state.tracks if tr.id == "tq")
    assert [(c.start, c.length) for c in track.clips] == [(48000 + 2 * RATE, 2 * RATE)]


def test_the_pre_roll_is_not_counted_in_where_the_clip_lands(session):
    rs = started(offline(session))
    session.edit("add_track", {"track_id": "tq", "name": "Questions"})
    rs.start(device=None, at=0, cart_track="tq",
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    rs._status["preroll_frames"] = RATE  # the take's clock started one second early
    path = recordings(session).parent / "q.wav"
    sf.write(path, np.full(RATE, 0.1, dtype=np.float32), RATE, subtype="PCM_16")
    entry_id = session.material_copy(session.store.import_batch(
        [str(path)], copy=False)[0].media.id)["entry"]["id"]
    rs._position = 3 * RATE
    assert rs.cart_log(entry_id)["at"] == 2 * RATE


def test_playing_without_a_cart_track_logs_nothing(session):
    rs = started(offline(session))
    rs.start(device=None, at=0,
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    with pytest.raises(RecordError) as e:
        rs.cart_log("anything")
    assert e.value.key == "error.record.no_cart_track"


def test_the_cart_track_cannot_be_a_track_that_records(session):
    rs = started(offline(session))
    session.edit("add_track", {"track_id": "t1", "name": "Host"})
    with pytest.raises(RecordError) as e:
        rs.start(device=None, at=0, cart_track="t1",
                 channels=[{"channel": 1, "track_id": "t1", "name": ""}])
    assert e.value.key == "error.record.cart_track_records"


def test_a_new_cart_track_is_made_with_the_take_tracks(session):
    rs = started(offline(session))
    rs.start(device=None, at=0, cart_track="new",
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    assert [tr.name for tr in session.state.tracks] == ["Olli", "Questions"]


def test_a_clip_played_when_nothing_records_is_refused(session):
    rs = offline(session)
    with pytest.raises(RecordError) as e:
        rs.cart_log("anything")
    assert e.value.key == "error.record.not_recording"


def test_the_recording_delay_trims_the_head_of_the_take_so_it_lines_up(session):
    # Playing the other tracks while recording: what the performer reacted to was heard
    # `latency_frames` late, so the take's head is cut by that much (file untouched).
    folder = recordings(session)
    plan = rt.TakePlan("Take 1", RATE, None, "Olli", 1, latency_frames=480)
    write_take(folder, plan=plan)
    offline(session).import_take("Take 1")
    clip = session.state.tracks[0].clips[0]
    assert clip.start == RATE
    assert clip.offset == 480
    assert clip.length == RATE - 480


def test_the_plan_keeps_the_recording_delay_on_disk(session):
    folder = recordings(session)
    plan = rt.TakePlan("Take 1", 0, None, "Olli", 1, latency_frames=960)
    write_take(folder, plan=plan)
    assert rt.read_plan(folder, "Take 1").latency_frames == 960
    # a plan written before this field reads as no delay
    write_take(folder, "Old", plan=rt.TakePlan("Old", 0, None, "Olli", 1))
    assert rt.read_plan(folder, "Old").latency_frames == 0


class MonitorEngine(NoEngine):
    """Records what the server asks of the engine while a take runs."""

    def __init__(self):
        super().__init__()
        self.played = []
        self.overlays = []

    def play(self, at=None, until=None, **kw):
        self.played.append(at)

    def set_silence_overlay(self, ranges):
        self.overlays.append(ranges)


def test_play_the_other_tracks_while_recording_is_opt_in_and_silences_the_recorded_ones(
        session, tmp_path, recorder):
    engine = MonitorEngine()
    rs = live(session, recorder)
    try:
        with api(session, tmp_path, rs, engine) as c:
            r = c.post("/api/record/start", json={
                "device": {"index": 0, "name": "Fake Mic"}, "channel": 2,
                "track_id": "new", "name": "Guest", "at": 4800, "play_others": True,
                "latency_ms": 20})
            assert r.status_code == 200, r.text
            assert engine.stops == 0  # not stopped: the other tracks play
            assert engine.played == [4800]
            recorded = {t.id for t in session.state.tracks if t.name == "Guest"}
            assert set(engine.overlays[-1]) == recorded  # the recorded track is silent
            time.sleep(0.5)
            c.post("/api/record/stop", json={"mode": "two_step"})
            assert engine.stops == 1
            assert engine.overlays[-1] is None
    finally:
        rs.close()


def test_without_the_option_a_take_still_stops_playback(session, tmp_path, recorder):
    engine = MonitorEngine()
    rs = live(session, recorder)
    try:
        with api(session, tmp_path, rs, engine) as c:
            r = c.post("/api/record/start", json={
                "device": {"index": 0, "name": "Fake Mic"}, "channel": 2,
                "track_id": "new", "name": "Guest", "at": 0})
            assert r.status_code == 200, r.text
            assert engine.stops == 1
            assert engine.played == []
            assert engine.overlays == []
    finally:
        rs.close()


def test_cart_end_and_replacement_only_trim_logged_clips(session):
    rs = started(offline(session))
    session.edit("add_track", {"track_id": "tq", "name": "Questions"})
    rs.start(device=None, at=RATE, cart_track="tq",
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    path = recordings(session).parent / "cart.wav"
    sf.write(path, np.full(RATE * 2, 0.1, dtype=np.float32), RATE)
    media = session.store.import_batch([str(path)], copy=False)[0].media
    entry = session.material_copy(media.id)["entry"]["id"]
    rs._position = RATE
    first = rs.cart_log(entry, gain_db=3)
    take_track = next(tr for tr in session.state.tracks if tr.id != "tq")
    rs._position = RATE + RATE // 2
    second = rs.cart_log(entry, gain_db=-2)
    clips = next(tr for tr in session.state.tracks if tr.id == "tq").clips
    assert clips[0].length == RATE // 2
    assert clips[0].gain_db == 3
    assert clips[1].gain_db == -2
    assert first["clip_ids"] != second["clip_ids"]
    rs._position += RATE // 4
    rs.cart_end(second["clip_ids"])
    clips = next(tr for tr in session.state.tracks if tr.id == "tq").clips
    assert clips[1].length == RATE // 4
    assert session.state.track(take_track.id) == take_track
    with pytest.raises(EditError):
        session.edit("trim_clips", {"clip_ids": [clips[0].id], "end": 1})


def test_cart_end_rejects_unowned_clip_ids(session):
    rs = offline(session)
    with pytest.raises(RecordError):
        rs.cart_end(["unrelated"])


def test_cart_take_end_uses_final_segment_clock_not_last_meter(session, monkeypatch):
    rs = started(offline(session))
    session.edit("add_track", {"track_id": "tq", "name": "Questions"})
    rs.start(device=None, at=0, cart_track="tq",
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    path = recordings(session).parent / "cart-final.wav"
    sf.write(path, np.full(RATE * 2, 0.1, dtype=np.float32), RATE)
    media = session.store.import_batch([str(path)], copy=False)[0].media
    entry = session.material_copy(media.id)["entry"]["id"]
    play = rs.cart_log(entry)
    rs._position = 100
    monkeypatch.setattr(rs, "_sidecar", lambda _: {
        "segments": [{"start_frame": 200, "files": {"Olli": {"frames": 300}}}]})
    monkeypatch.setattr(rs, "_import_later", lambda _: None)
    rs._on_event({"event": "stopped", "folder": str(rs.folder),
                  "take": rs._status["take"], "frames": 300})
    assert session.state.track("tq").clips[0].length == 500
    rs.cart_end(play["clip_ids"])  # a late page notification is harmless


def test_cart_voice_estimate_expires_and_falls_back_to_reference(session, monkeypatch):
    rs = started(offline(session))
    rs._cart_track = "tq"
    rs._status = {"state": "recording", "folder": str(rs.folder)}
    calls = []
    monkeypatch.setattr(session, "clipboard_preview",
                        lambda entry, **kwargs: calls.append(kwargs))
    rs.cart_preview("e", 2)
    assert calls[-1] == {"cart_voice": None, "cart_trim": 2, "cart_track": "tq"}
    rs._on_event({"event": "level", "peak_dbfs": [-20, -100], "position_frames": 10})
    rs.cart_preview("e")
    assert calls[-1]["cart_voice"] == pytest.approx(-34)
    rs._voice_levels = [(time.monotonic() - 4, -20)]
    rs.cart_preview("e")
    assert calls[-1]["cart_voice"] is None


def test_cart_preview_api_stores_the_played_gain_and_end_is_scoped(session, tmp_path,
                                                                  monkeypatch):
    rs = started(offline(session))
    session.edit("add_track", {"track_id": "tq", "name": "Questions"})
    rs.start(device=None, at=0, cart_track="tq",
             channels=[{"channel": 1, "track_id": None, "name": "Olli"}])
    path = recordings(session).parent / "cart-api.wav"
    sf.write(path, np.full(RATE * 2, 0.01, dtype=np.float32), RATE)
    media = session.store.import_batch([str(path)], copy=False)[0].media
    entry = session.material_copy(media.id)["entry"]["id"]
    monkeypatch.setattr(session, "_preview_reference", lambda *_: (-23, None))
    monkeypatch.setattr(clipboard_level, "entry_level", lambda *_: (-33, -20))
    engine = NoEngine()
    previews = []
    engine.play_preview = lambda p, **kwargs: previews.append((p, kwargs))
    engine.stop_preview = lambda: None
    with api(session, tmp_path, rs, engine) as client:
        result = client.post(f"/api/clipboard/{entry}/preview",
                             json={"cart_trim": 2, "limit": False})
        assert result.status_code == 200
        body = result.json()
        assert body["attenuation_db"] == 12
        assert previews[0][0].master_gain_db == 12
        clip = session.state.track("tq").clips[0]
        assert clip.gain_db == 12
        assert body["cart"]["clip_ids"] == [clip.id]
        rs._position = 1234
        result = client.post("/api/clipboard/preview/stop")
        assert result.status_code == 200
        assert session.state.track("tq").clips[0].length == 1234
        assert client.post("/api/record/cart/end",
                           json={"clip_ids": [clip.id]}).status_code == 200
        assert client.post("/api/record/cart/end",
                           json={"clip_ids": ["other"]}).status_code == 400


def test_cart_level_cache_tracks_master_gain(session, tmp_path, monkeypatch):
    session.edit("add_track", {"track_id": "tq", "name": "Questions"})
    path = tmp_path / "cart-cache.wav"
    sf.write(path, np.full(RATE, 0.01, dtype=np.float32), RATE)
    media = session.store.import_batch([str(path)], copy=False)[0].media
    entry = session.material_copy(media.id)["entry"]["id"]
    monkeypatch.setattr(session, "_preview_reference", lambda *_: (-23, None))
    monkeypatch.setattr(clipboard_level, "entry_level",
                        lambda p, _: (-33 + p.master_gain_db, -20 + p.master_gain_db))
    _, _, gain = session.clipboard_preview(entry, cart_track="tq")
    assert gain == 10
    session.edit("set_master", {"gain_db": -6})
    _, _, gain = session.clipboard_preview(entry, cart_track="tq")
    assert gain == 16  # changing the project master changes the measured entry


def test_record_levels_carry_lufs_separately_from_peak_clipping(session):
    from types import SimpleNamespace  # noqa: PLC0415

    rs = offline(session)
    seen = []
    rs._input_loudness = SimpleNamespace(
        observe=lambda *args: seen.append(args), read=lambda: [-23.0, -16.0],
        reset=lambda: None, close=lambda: None)
    status = {'state': 'recording', 'take': 'Take 1', 'folder': str(rs.folder),
              'channels': [{'channel': 1, 'name': 'Host'},
                           {'channel': 2, 'name': 'Guest'}]}
    try:
        rs._status = status
        view = rs._view(status, True)
        assert seen
        assert view['short_term_lufs'] == [-23.0, -16.0]
        rs._on_event({'event': 'level', 'peak_dbfs': [-1.0, 0.0],
                      'clipped': [False, True], 'position_frames': RATE})
        event = rs.publish.kinds('level')[-1]
        assert event['short_term_lufs'] == [-23.0, -16.0]
        assert event['peak_dbfs'] == [-1.0, 0.0]
        assert event['clipped'] == [False, True]
    finally:
        rs.close()


def test_recording_lufs_reaches_live_subscribers_from_flushed_audio(session, recorder):
    published = Published()
    rs = live(session, recorder, published)
    try:
        rs.start(device=None, channel=1, track_id=None, name="Host", at=0)
        def has_loudness():
            return any(m.get("short_term_lufs")
                       and m["short_term_lufs"][0] is not None
                       for m in published.kinds("level"))
        wait_until(has_loudness, timeout=15)
        assert rs.status()["recording"]
        assert all("peak_dbfs" in message and "clipped" in message
                   for message in published.kinds("level"))
        rs.stop("one_click", 0)
    finally:
        rs.close()


def test_live_transcript_words_arrive_while_the_take_runs(session, recorder):
    """Owner, 2026-11-01: the take's newest seconds are searchable during the take."""
    published = Published()
    rs = RecordSession(
        session, published,
        connect=lambda: RecorderClient.connect(recorder.socket_path, timeout=20),
        spawn=no_spawn, retry_s=0.1,
        live_engine_factory=lambda: (lambda audio, rate: [
            {"word": "terveiset", "start": 1.0, "end": 1.5},
            {"word": "kokouksesta", "start": 1.6, "end": 2.2}]))
    try:
        view = rs.start(device={"index": 0, "name": "Fake Mic"}, channel=1,
                        track_id=None, name="Olli", at=0)
        assert view["recording"]
        # The first full 5 s chunk lands while the take still records.
        wait_until(lambda: published.kinds("live_transcript"), timeout=30)
        assert view["recording"] or rs.status()["recording"]
        hits = rs.live_transcript_search("kokouksesta")
        assert [h["w"] for h in hits] == ["kokouksesta"]
        assert [w["w"] for w in rs.live_transcript_words()] == ["terveiset", "kokouksesta"]
        rs.stop("two_step")
        # Over: the live store is gone; the post-hoc worker owns the take's text.
        wait_until(lambda: not rs.status()["recording"], timeout=20)
        assert rs.live_transcript_words() == []
    finally:
        rs.close()


def test_no_engine_factory_no_live_transcript(session, recorder):
    published = Published()
    rs = live(session, recorder, published)
    try:
        rs.start(device={"index": 0, "name": "Fake Mic"}, channel=1,
                 track_id=None, name="Olli", at=0)
        time.sleep(1.0)
        assert published.kinds("live_transcript") == []
        assert rs.live_transcript_words() == []
        rs.stop("two_step")
    finally:
        rs.close()
