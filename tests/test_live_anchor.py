"""The live channel's playhead anchors (precise cursor, 2026-10-20), no device.

The browser extrapolates the playhead from an anchor; the server sends one at
once on every transport change and a correction every ``correct_every`` while
playing, never an older one after a newer one, answers pings for the clock
offset, and reads the engine on a thread of its own: a saturated default
executor must not hold the playhead up.
"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import messages
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


class AnchoredEngine(FakeEngine):
    """The fake engine with the anchor fields: ``seq`` changes on every transport
    change, ``t`` is when the position was heard."""

    def __init__(self):
        super().__init__()
        self.seq = 0
        self.t = None
        self.speed = 1.0
        self.preview = False
        self.mix_preview = None
        self.preview_seq = 0
        self.end = None

    def status(self):
        out = super().status()
        out.update(seq=self.seq, t=time.monotonic() if self.t is None else self.t,
                   speed=self.speed, end=self.end, skip=[], loop=None, rate=48000,
                   preview=self.preview, mix_preview=self.mix_preview,
                   preview_seq=self.preview_seq)
        return out

    def play(self, *args, **kwargs):
        super().play(*args, **kwargs)
        self.seq += 1

    def stop(self):
        super().stop()
        self.seq += 1

    def seek(self, frame):
        super().seek(frame)
        self.seq += 1


@pytest.fixture
def engine():
    return AnchoredEngine()


def opened(ws):
    ws.receive_json()  # hello
    ws.receive_json()  # jobs


def next_anchor(ws, limit=500):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == "anchor":
            return msg
    raise AssertionError("no anchor")


def test_a_transport_change_sends_an_anchor_at_once(session, engine, tmp_path):
    # a poll period far longer than the test: the anchor can only come from the request
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=1000.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        c.post("/api/transport", json={"action": "play", "at": 4800})
        msg = next_anchor(ws)
        assert msg["position"] == 4800
        assert msg["playing"] is True
        assert msg["seq"] == engine.seq
        assert msg["speed"] == 1.0
        assert isinstance(msg["t"], float)
        assert isinstance(msg["now"], float)
        assert msg["now"] >= msg["t"] - 1


def test_corrections_go_out_at_their_period_not_every_tick(session, engine, tmp_path):
    # no timing in the assertion: a period far longer than the test sends no
    # correction however many ticks there are; a transport change still goes at once
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     meter_every=0.0, correct_every=1000.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        engine.playing, engine.position = True, 100
        first = next_anchor(ws)
        assert first["playing"]
        meters, anchors = 0, 0
        while meters < 20:
            engine.position += 100
            msg = ws.receive_json()
            meters += msg["type"] == "meter"
            anchors += msg["type"] == "anchor"
        assert anchors == 0
        engine.seq += 1  # a skip run restarted, a loop changed: at once
        assert next_anchor(ws)["seq"] == engine.seq


def test_corrections_flow_while_playing(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     correct_every=0.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        engine.playing = True
        seen = set()
        for _ in range(5):
            engine.position += 480
            seen.add(next_anchor(ws)["position"])
        assert len(seen) >= 3


def test_after_a_stop_no_older_anchor_says_playing(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     correct_every=0.0, meter_every=0.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        c.post("/api/transport", json={"action": "play", "at": 0})
        while not next_anchor(ws)["playing"]:
            pass
        reply = c.post("/api/transport", json={"action": "stop"}).json()
        stop_seq = engine.seq
        assert reply["playing"] is False
        # a reading taken before the stop and sent after it: its older sequence
        # number must not put the playhead back in motion
        engine.seq, engine.playing = stop_seq - 1, True
        msg = next_anchor(ws)
        while msg["seq"] < stop_seq:  # what went out before the stop
            msg = next_anchor(ws)
        assert msg["seq"] == stop_seq
        assert not msg["playing"]
        for _ in range(30):  # the meter goes out every tick: thirty ticks
            msg = ws.receive_json()
            assert not (msg["type"] == "anchor" and msg["playing"])
        engine.seq = stop_seq + 1  # a real play after it goes through
        msg = next_anchor(ws)
        assert msg["seq"] == stop_seq + 1
        assert msg["playing"]


def test_the_channel_answers_a_ping_with_its_clock(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.01)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        before = time.monotonic()
        ws.send_json({"type": "ping", "c": 1234.5})
        msg = ws.receive_json()
        while msg["type"] != "pong":
            msg = ws.receive_json()
        assert msg["c"] == 1234.5
        assert before <= msg["s"] <= time.monotonic()


def test_a_clipboard_preview_never_moves_the_playhead(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     correct_every=0.0, meter_every=0.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        engine.position = 7000
        engine.seq += 1  # a seek from another window
        assert next_anchor(ws)["position"] == 7000
        engine.preview, engine.playing, engine.position = True, True, 10
        engine.seq += 1
        for _ in range(20):
            msg = ws.receive_json()
            assert not (msg["type"] == "anchor" and msg["playing"])


def next_of(ws, kind, limit=500):
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == kind:
            return msg
    raise AssertionError(f"no {kind}")


def test_a_clipboard_preview_has_its_own_progress_messages(session, engine, tmp_path):
    # The Clipboard chip draws the preview's progress: "preview" messages carry the
    # preview's heard frame, its end (the excerpt's length) and the anchor timing;
    # when the preview ends one says it stopped, with the engine's transport version.
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     correct_every=0.0, meter_every=1000.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        engine.preview, engine.playing, engine.position = True, True, 480
        engine.end = 9600
        engine.seq += 1
        msg = next_of(ws, "preview")
        assert msg["playing"] is True
        assert msg["position"] == 480
        assert msg["end"] == 9600
        assert msg["seq"] == engine.seq
        assert isinstance(msg["t"], float)
        engine.preview, engine.playing = False, False
        engine.seq += 1
        msg = next_of(ws, "preview")
        while msg["playing"]:
            msg = next_of(ws, "preview")
        assert msg["seq"] == engine.seq


def test_the_engine_is_never_read_on_the_default_executor(
        session, engine, tmp_path, monkeypatch):
    # Whatever is handed to the event loop's default executor (asyncio.to_thread
    # uses it, and so does other work) can queue behind a saturated pool: the
    # live channel must read the engine on a thread of its own.
    real = asyncio.BaseEventLoop.run_in_executor
    handed = []

    def recording(self, executor, func, *args):
        if executor is None:
            handed.append((func, *getattr(func, "args", ()), *args))
        return real(self, executor, func, *args)

    monkeypatch.setattr(asyncio.BaseEventLoop, "run_in_executor", recording)
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     correct_every=0.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        engine.playing, engine.position = True, 4800
        for _ in range(3):
            assert next_anchor(ws)["playing"]
            engine.position += 480
    assert not [job for job in handed if engine.status in job]


def test_a_preview_mixed_into_playback_keeps_the_timeline_anchors_and_adds_its_own(
        session, engine, tmp_path):
    # The preview is one more voice: the timeline still says playing, with its own
    # position and version, and the chip's progress comes as "preview" messages in
    # the voice's own frames and version.
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.005,
                     correct_every=0.0, meter_every=1000.0)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        opened(ws)
        engine.playing, engine.position, engine.seq = True, 96_000, 5
        assert next_anchor(ws)["playing"] is True
        engine.mix_preview = {"playing": True, "position": 480, "t": time.monotonic(),
                              "end": 9600, "seq": 8}
        engine.preview_seq = 8
        msg = next_of(ws, "preview")
        assert msg["playing"] is True
        assert msg["position"] == 480
        assert msg["end"] == 9600
        assert msg["seq"] == 8
        anchor = next_anchor(ws)
        assert anchor["playing"] is True
        assert anchor["position"] == 96_000
        assert anchor["seq"] == 5
        engine.mix_preview, engine.preview_seq = None, 9
        msg = next_of(ws, "preview")
        while msg["playing"]:
            msg = next_of(ws, "preview")
        assert msg["seq"] == 9
