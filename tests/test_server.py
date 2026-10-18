"""The HTTP API (WP3): FastAPI TestClient, the engine replaced by a fake."""

import json
import socket
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import uvicorn
from fastapi.testclient import TestClient
from test_history import heavy_hour, register

from kuulas import cli, messages
from kuulas.engine import EngineError
from kuulas.playplan import PlaybackRequestError
from kuulas.server import create_app, pick_language
from kuulas.session import Session

RATE = 48000
WORDS = [{"word": "hello", "start": 0.1, "end": 0.4},
         {"word": "there", "start": 0.5, "end": 0.9}]


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class FakeEngine:
    """What the API needs of an Engine: the public surface, no device."""

    def __init__(self, session=None):
        self.calls: list[tuple] = []
        self.position = 0
        self.playing = False
        self.until = None
        self.notices: list[dict] = []
        self.fail_play = False

    def status(self):
        return {"playing": self.playing, "position": self.position,
                "until": self.until, "notices": list(self.notices)}

    def play(self, at=None, until=None, *, rate=1.0, preserve_pitch=True, skip=None):
        self.calls.append(("play", at, until))
        self.play_options = {"rate": rate, "preserve_pitch": preserve_pitch,
                             "skip": skip}
        if rate not in (1.0, -1.0) and preserve_pitch:  # as the real engine
            raise PlaybackRequestError("error.engine.stretch_unavailable", speed=rate)
        if self.fail_play:
            raise EngineError("error.engine.no_device")
        self.playing, self.until = True, until
        if at is not None:
            self.position = at

    def stop(self):
        self.calls.append(("stop",))
        self.playing = False

    def seek(self, frame):
        self.calls.append(("seek", frame))
        self.position = frame

    def scrub(self, frame):
        self.calls.append(("scrub", frame))
        self.position = frame

    def close(self):
        self.calls.append(("close",))


def wav(path: Path, seconds: float = 1.0, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def client(session, engine, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, engine, language="en", ui_dir=ui)) as c:
        yield c


@pytest.fixture
def loaded(client, tmp_path):
    """A project with one track holding one second of audio."""
    r = client.post("/api/import", json={"paths": [str(wav(tmp_path / "a.wav"))],
                                         "copy": False})
    assert r.status_code == 200, r.text
    return r.json()


def media_id(body) -> str:
    return body["project"]["media"][0]["id"]


# -- state and edits -----------------------------------------------------------


def test_state_shape(client):
    body = client.get("/api/state").json()
    assert body["project"]["rate"] == RATE
    assert isinstance(body["head"], str)
    assert body["can_undo"] is False
    assert body["can_redo"] is False
    assert body["missing"] == []


def test_edit_applies_an_op_and_returns_the_state(client, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    r = client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                       "args": {"track_id": track, "gain_db": -6.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["tracks"][0]["gain_db"] == -6.0
    assert body["can_undo"] is True
    assert body["head"] != loaded["head"]
    assert client.get("/api/history").json()["nodes"][-1]["label"] == "quieter"


def test_edit_error_is_400_with_key_and_text(client):
    r = client.post("/api/edit", json={"op": "set_track",
                                       "args": {"track_id": "nope", "gain_db": 0}})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["key"] == "error.edit.no_track"
    assert err["params"] == {"track_id": "nope"}
    assert err["text"] == "There is no track nope."


def test_unknown_op_is_400(client):
    r = client.post("/api/edit", json={"op": "no_such_op", "args": {}})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.edit.unknown"


def test_malformed_request_is_400_in_the_error_shape(client):
    r = client.post("/api/edit", json={"args": {}})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.server.bad_request"


def test_error_text_follows_accept_language(client):
    r = client.post("/api/edit", json={"op": "set_track", "args": {"track_id": "x"}},
                    headers={"Accept-Language": "fi-FI,fi;q=0.9,en;q=0.5"})
    err = r.json()["error"]
    assert err["key"] == "error.edit.no_track"
    assert err["text"] == "Raitaa x ei ole."
    # and the next request without a header is back in the default language
    r = client.post("/api/edit", json={"op": "set_track", "args": {"track_id": "x"}})
    assert r.json()["error"]["text"] == "There is no track x."


def test_pick_language():
    assert pick_language("fi-FI,fi;q=0.9", "en") == "fi"
    assert pick_language("sv, fi;q=0.8, en;q=0.5", "en") == "fi"
    assert pick_language("en;q=0.2, fi;q=0.9", "en") == "fi"
    assert pick_language("de", "fi") == "fi"
    assert pick_language(None, "fi") == "fi"
    assert pick_language("*;q=0.1,garbage;;", "fi") == "fi"


def test_unexpected_failure_is_500_and_the_server_lives(client, session, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(session, "edit", boom)
    r = client.post("/api/edit", json={"op": "set_track", "args": {}})
    assert r.status_code == 500
    assert r.json()["error"]["key"] == "error.server.internal"
    assert client.get("/api/state").status_code == 200


def test_command(client, loaded):
    r = client.post("/api/command", json={"name": "relink", "args": {}})
    assert r.status_code == 200
    assert r.json()["project"]["tracks"]
    r = client.post("/api/command", json={"name": "nope", "args": {}})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.edit.unknown"


def test_undo_and_redo(client, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    undone = client.post("/api/undo").json()
    assert undone["project"]["tracks"][0]["gain_db"] == 0.0
    assert undone["can_redo"] is True
    redone = client.post("/api/redo").json()
    assert redone["project"]["tracks"][0]["gain_db"] == -6.0
    # nothing to redo: not an error, the state comes back unchanged
    again = client.post("/api/redo")
    assert again.status_code == 200
    assert again.json()["head"] == redone["head"]


def test_history_lists_the_steps(client, loaded):
    body = client.get("/api/history").json()
    assert body["head"] == loaded["head"]
    assert [n["id"] for n in body["nodes"]][-1] == body["head"]
    assert body["nodes"][0]["label"] == "new project"


def test_restore_adds_a_step_instead_of_rewinding(client, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    before = client.get("/api/history").json()["nodes"]
    client.post("/api/edit", json={"op": "set_track",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    r = client.post("/api/restore", json={"node": loaded["head"]})
    assert r.status_code == 200
    body = r.json()
    assert body["project"]["tracks"][0]["gain_db"] == 0.0
    assert "context" in body
    nodes = client.get("/api/history").json()["nodes"]
    assert len(nodes) == len(before) + 2  # the edit, and the restore
    assert nodes[-1]["label"].startswith("restored to")
    # the step that was current before the restore is still reachable
    assert body["can_undo"] is True
    assert client.post("/api/undo").json()["project"]["tracks"][0]["gain_db"] == -6.0


def test_restore_of_an_unknown_step_is_404(client):
    r = client.post("/api/restore", json={"node": "nope"})
    assert r.status_code == 404
    assert r.json()["error"]["key"] == "error.history.no_step"


# -- import and upload ---------------------------------------------------------


def test_import_returns_the_report_per_file(client, tmp_path):
    good = wav(tmp_path / "good.wav")
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"")
    r = client.post("/api/import", json={"paths": [str(good), str(bad)], "copy": True})
    assert r.status_code == 200
    body = r.json()
    assert len(body["project"]["tracks"]) == 1
    ok, failed = body["report"]
    assert ok["ok"] is True
    assert ok["path"] == str(good)
    assert ok["media"] == body["project"]["media"][0]["id"]
    assert failed["ok"] is False
    assert failed["error"]["key"] == "error.media.empty"
    assert "empty" in failed["error"]["text"]


def test_import_of_only_bad_files_is_500_with_the_report(client, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"")
    r = client.post("/api/import", json={"paths": [str(bad)]})
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["key"] == "error.media.empty"
    assert body["report"][0]["ok"] is False
    assert client.get("/api/state").json()["project"]["tracks"] == []


def test_upload_imports_the_file(client, session, tmp_path):
    src = wav(tmp_path / "upload me.wav")
    with src.open("rb") as f:
        r = client.post("/api/upload",
                        files=[("files", ("upload me.wav", f, "audio/wav"))])
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["project"]["media"]) == 1
    assert body["report"][0]["ok"] is True
    saved = session.package.path / "uploads" / "upload me.wav"
    assert saved.exists()
    assert not list((session.package.path / "uploads").glob("*.partial"))


def test_upload_never_overwrites_and_keeps_only_the_file_name(client, session, tmp_path):
    a = wav(tmp_path / "a.wav", seed=1)
    b = wav(tmp_path / "b.wav", seed=2)
    for src, claimed in ((a, "take.wav"), (b, "../../take.wav")):
        with src.open("rb") as f:
            assert client.post("/api/upload", files=[("files", (claimed, f))]
                               ).status_code == 200
    uploads = sorted(p.name for p in (session.package.path / "uploads").iterdir())
    assert len(uploads) == 2
    assert "take.wav" in uploads
    assert not (session.package.path.parent / "take.wav").exists()


def test_upload_without_files_is_400(client):
    r = client.post("/api/upload")
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.server.bad_request"


# -- peaks ---------------------------------------------------------------------


def test_peak_tiles_are_binary_with_etag_and_long_cache(client, loaded):
    media = media_id(loaded)
    r = client.get(f"/api/peaks/{media}/256/0")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    pairs = np.frombuffer(r.content, dtype="<f4").reshape(-1, 2)
    assert 0 < len(pairs) <= 1024
    assert (pairs[:, 0] <= pairs[:, 1]).all()
    assert r.headers["etag"]
    cache = r.headers["cache-control"]
    assert "immutable" in cache
    assert "max-age=31536000" in cache


def test_peak_tile_matches_the_media_store(client, session, loaded):
    media = media_id(loaded)
    body, etag = session.store.peak_tile(media, 1024, 0)
    r = client.get(f"/api/peaks/{media}/1024/0")
    assert r.content == body
    assert r.headers["etag"] == f'"{etag}"'


def test_peak_tile_304_on_if_none_match(client, loaded):
    media = media_id(loaded)
    first = client.get(f"/api/peaks/{media}/256/0")
    etag = first.headers["etag"]
    again = client.get(f"/api/peaks/{media}/256/0", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == etag
    listed = client.get(f"/api/peaks/{media}/256/0",
                        headers={"If-None-Match": f'"x", W/{etag}'})
    assert listed.status_code == 304
    other = client.get(f"/api/peaks/{media}/256/0", headers={"If-None-Match": '"old"'})
    assert other.status_code == 200


def test_peak_tile_unknown_media_level_or_tile_is_404(client, loaded):
    media = media_id(loaded)
    for url in ("/api/peaks/nope/256/0", f"/api/peaks/{media}/300/0",
                f"/api/peaks/{media}/256/999"):
        r = client.get(url)
        assert r.status_code == 404, url
        assert r.json()["error"]["key"].startswith("error.")


# -- words and transcripts -----------------------------------------------------


def test_transcript_import_then_words(client, loaded):
    media = media_id(loaded)
    assert client.get("/api/words").json() == {"words": []}
    r = client.post(f"/api/transcript/{media}", json=WORDS)
    assert r.status_code == 200
    assert r.json()["can_undo"] is True
    words = client.get("/api/words").json()["words"]
    assert [w["w"] for w in words] == ["hello", "there"]


def test_words_name_the_people_they_refer_to(client, loaded, session):
    media = media_id(loaded)
    client.post(f"/api/transcript/{media}", json=WORDS)
    assert "people" not in client.get("/api/words").json()
    pid = session.create_person("Anna Virtanen")
    session.set_media_person(media, pid)
    body = client.get("/api/words").json()
    assert {w["person"] for w in body["words"]} == {pid}
    assert body["people"] == {pid: "Anna Virtanen"}


def test_transcript_import_accepts_the_whisper_shape(client, loaded):
    media = media_id(loaded)
    segments = {"segments": [{"words": WORDS}]}
    assert client.post(f"/api/transcript/{media}", json=segments).status_code == 200
    assert len(client.get("/api/words").json()["words"]) == 2


def test_transcript_import_errors(client, loaded):
    media = media_id(loaded)
    nothing = client.post(f"/api/transcript/{media}", json=[])
    assert nothing.status_code == 400
    assert nothing.json()["error"]["key"] == "error.transcript.empty"
    junk = client.post(f"/api/transcript/{media}", json=[1, 2])
    assert junk.status_code == 400
    assert junk.json()["error"]["key"] == "error.transcript.unreadable"
    unknown = client.post("/api/transcript/nope", json=WORDS)
    assert unknown.status_code == 404


def test_word_correction_is_a_new_revision(client, loaded):
    media = media_id(loaded)
    client.post(f"/api/transcript/{media}", json=WORDS)
    r = client.put("/api/word", json={"media": media, "index": 1, "w": "world"})
    assert r.status_code == 200
    assert [w["w"] for w in client.get("/api/words").json()["words"]] == [
        "hello", "world"]
    client.post("/api/undo")
    assert [w["w"] for w in client.get("/api/words").json()["words"]] == [
        "hello", "there"]


def test_word_correction_errors(client, loaded):
    media = media_id(loaded)
    client.post(f"/api/transcript/{media}", json=WORDS)
    bad = client.put("/api/word", json={"media": media, "index": 9, "w": "x"})
    assert bad.status_code == 400
    assert bad.json()["error"]["key"] == "error.edit.no_word"
    unknown = client.put("/api/word", json={"media": "nope", "index": 0, "w": "x"})
    assert unknown.status_code == 404


# -- transport -----------------------------------------------------------------


def test_transport_get_is_the_engine_status(client, engine):
    engine.position = 1234
    assert client.get("/api/transport").json()["position"] == 1234


def test_transport_post_drives_the_engine(client, engine):
    r = client.post("/api/transport", json={"action": "play", "at": 100, "until": 900})
    assert r.status_code == 200
    assert r.json()["playing"] is True
    client.post("/api/transport", json={"action": "seek", "at": 500})
    client.post("/api/transport", json={"action": "scrub", "at": 600})
    r = client.post("/api/transport", json={"action": "stop"})
    assert r.json()["playing"] is False
    assert engine.calls == [("play", 100, 900), ("seek", 500), ("scrub", 600),
                            ("stop",)]


def test_transport_errors(client, engine):
    r = client.post("/api/transport", json={"action": "rewind"})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.server.bad_transport"
    r = client.post("/api/transport", json={"action": "seek"})
    assert r.status_code == 400
    engine.fail_play = True
    r = client.post("/api/transport", json={"action": "play"})
    assert r.status_code == 500
    assert r.json()["error"]["key"] == "error.engine.no_device"


def test_transport_play_takes_a_skip_list(client, engine):
    r = client.post("/api/transport", json={"action": "play", "at": 100, "until": 900,
                                            "skip": [[300, 500], [600, 650]]})
    assert r.status_code == 200
    assert engine.calls == [("play", 100, 900)]
    assert engine.play_options == {"rate": 1.0, "preserve_pitch": True,
                                   "skip": ((300, 500), (600, 650))}


def test_transport_play_without_skip_plays_everything(client, engine):
    client.post("/api/transport", json={"action": "play", "at": 100})
    assert engine.play_options["skip"] == ()


@pytest.mark.parametrize("skip", [[[500, 300]], [[1]], [[1, 2, 3]], [[-5, 10]]])
def test_transport_refuses_a_malformed_skip_with_a_translated_400(client, engine, skip):
    r = client.post("/api/transport", json={"action": "play", "at": 0, "skip": skip})
    assert r.status_code == 400
    error = r.json()["error"]
    assert error["key"] == "error.engine.bad_skip"
    assert error["text"] != error["key"]
    assert engine.calls == []  # nothing played


def test_transport_refuses_a_skip_that_is_not_a_list(client, engine):
    r = client.post("/api/transport", json={"action": "play", "skip": "soon"})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.server.bad_request"
    assert engine.calls == []


def test_transport_tape_speed_and_the_refused_pitch_kept_speed(client, engine):
    r = client.post("/api/transport", json={"action": "play", "at": 0, "speed": -2.0,
                                            "preserve_pitch": False})
    assert r.status_code == 200
    assert engine.play_options["rate"] == -2.0
    r = client.post("/api/transport", json={"action": "play", "at": 0, "speed": 1.5})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.engine.stretch_unavailable"


# -- the push channel ----------------------------------------------------------


def test_live_says_hello_with_the_head(client, loaded):
    with client.websocket_connect("/api/live") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["head"] == loaded["head"]
        assert ws.receive_json() == {"type": "jobs", "jobs": []}


def test_live_delivers_a_state_changed_notice_after_an_edit(client, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    with client.websocket_connect("/api/live") as ws:
        ws.receive_json()
        ws.receive_json()
        body = client.post("/api/edit", json={
            "op": "set_track", "args": {"track_id": track, "gain_db": -3.0}}).json()
        note = ws.receive_json()
        assert note == {"type": "state_changed", "head": body["head"]}
        client.post("/api/undo")
        assert ws.receive_json()["head"] == loaded["head"]


def test_live_pushes_the_heard_position_while_playing(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.01)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        ws.receive_json()
        ws.receive_json()
        engine.playing, engine.position = True, 4800
        msg = ws.receive_json()
        assert msg == {"type": "position", "position": 4800, "playing": True}
        engine.playing, engine.position = False, 5000
        # a last position when playback stops, so the playhead lands exactly
        while msg["playing"]:
            msg = ws.receive_json()
        assert msg["position"] == 5000


def test_live_pushes_engine_notices_once(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path, tick=0.01)
    with TestClient(app) as c, c.websocket_connect("/api/live") as ws:
        ws.receive_json()
        ws.receive_json()
        engine.notices.append({"id": 1, "key": "notice.engine.block_failed",
                               "params": {"count": 2}, "text": "two blocks failed"})
        msg = ws.receive_json()
        assert msg == {"type": "notice", "id": 1, "key": "notice.engine.block_failed",
                       "params": {"count": 2}, "text": "two blocks failed"}
        engine.notices.append({"id": 2, "key": "k", "params": {}, "text": "t"})
        assert ws.receive_json()["id"] == 2  # not 1 again


# -- the page and the process --------------------------------------------------


def test_root_serves_a_translated_placeholder_without_a_ui(client):
    en = client.get("/")
    assert en.status_code == 200
    assert "text/html" in en.headers["content-type"]
    assert "coming" in en.text.lower()
    fi = client.get("/", headers={"Accept-Language": "fi"})
    assert 'lang="fi"' in fi.text
    assert "coming" not in fi.text.lower()


@pytest.mark.parametrize("lang", ["en", "fi"])
def test_locale_catalog_is_served_for_the_ui(client, lang):
    r = client.get(f"/api/locales/{lang}")
    assert r.status_code == 200
    assert r.json() == messages._CATALOGS[lang]


def test_unknown_locale_is_a_translated_404(client):
    r = client.get("/api/locales/xx", headers={"Accept-Language": "fi"})
    assert r.status_code == 404
    assert r.json()["error"]["key"] == "error.api.no_language"
    assert "xx" in r.json()["error"]["text"]


def test_ui_files_are_served_from_the_ui_folder(session, engine, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / "index.html").write_text("<p>the real ui</p>")
    (ui / "app.js").write_text("export {}")
    with TestClient(create_app(session, engine, language="en", ui_dir=ui)) as c:
        assert "the real ui" in c.get("/").text
        assert c.get("/app.js").text == "export {}"
        assert c.get("/api/state").status_code == 200


def test_server_binds_localhost_only(session, engine, tmp_path):
    app = create_app(session, engine, language="en", ui_dir=tmp_path)
    sock = cli.bind_local()
    try:
        config = cli.uvicorn_config(app, sock)
        assert isinstance(config, uvicorn.Config)
        assert config.host == "127.0.0.1"
        assert sock.getsockname()[0] == "127.0.0.1"
        assert sock.getsockname()[1] != 0
    finally:
        sock.close()


def test_open_creates_the_package_and_serves_on_localhost(tmp_path, monkeypatch):
    seen = {}

    def fake_run(self, sockets=None):
        seen["config"] = self.config
        seen["hosts"] = [s.getsockname()[0] for s in sockets]
        seen["exists"] = (tmp_path / "New.kuulas" / "manifest.json").exists()

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    assert cli.main(["open", str(tmp_path / "New.kuulas"), "--no-browser"]) == 0
    assert seen["config"].host == "127.0.0.1"
    assert seen["exists"]
    assert seen["hosts"] == ["127.0.0.1"]
    assert opened == []


def test_bind_local_gives_a_free_port_each_time():
    a, b = cli.bind_local(), cli.bind_local()
    try:
        assert a.getsockname()[1] != b.getsockname()[1]
        assert isinstance(a, socket.socket)
    finally:
        a.close()
        b.close()


# -- budget (ground rule 14) ---------------------------------------------------


def test_edit_round_trip_on_the_heavy_hour_is_under_50_ms(tmp_path, engine):
    s = Session(tmp_path / "Heavy.kuulas")
    try:
        project = heavy_hour()
        for m in project.media:
            register(s.history, m.id, m.frames)
        s.history.commit("heavy hour", project)
        ui = tmp_path / "ui"
        ui.mkdir()
        with TestClient(create_app(s, engine, language="en", ui_dir=ui)) as c:
            def edit(i: int) -> float:
                started = time.perf_counter()
                r = c.post("/api/edit", json={
                    "op": "set_track", "args": {"track_id": "t0", "gain_db": -i * 0.1}})
                body = r.json()  # the client has the new state when it has parsed it
                took = time.perf_counter() - started
                assert r.status_code == 200
                assert len(body["project"]["tracks"][0]["clips"]) == 301
                return took

            edit(0)  # one warm-up run: imports, first connection
            times = [edit(i) for i in range(1, 8)]  # best of 7 runs
        best = min(times)
        timings = ", ".join(f"{t * 1000:.1f} ms" for t in times)
        assert best < 0.050, (
            f"best was {best * 1000:.1f} ms (budget < 50 ms); runs: [{timings}]"
        )
    finally:
        s.close()


def test_json_responses_are_plain_json(client):
    r = client.get("/api/state")
    assert json.loads(r.content)["project"]["rate"] == RATE


def test_get_music_report_json(client):
    r = client.get("/api/music-report")
    assert r.status_code == 200
    assert "rows" in r.json()
    assert isinstance(r.json()["rows"], list)


def test_get_music_report_csv(client):
    r = client.get("/api/music-report?format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert "Order;Title;Artist" in r.text


def test_get_music_report_html(client):
    r = client.get("/api/music-report?format=html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<!DOCTYPE html>" in r.text
    assert "<table" in r.text


def test_get_music_report_bad_format_returns_400(client):
    r = client.get("/api/music-report?format=unsupported")
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.music_report.bad_format"


# -- the history panel's pages and what undo reports ----------------------------


def test_history_page_is_newest_first_and_pages_backwards(client, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    for g in (-1.0, -2.0, -3.0):
        client.post("/api/edit", json={"op": "set_track", "label": f"gain {g}",
                                       "args": {"track_id": track, "gain_db": g}})
    first = client.get("/api/history", params={"limit": 2}).json()
    assert [n["label"] for n in first["nodes"]] == ["gain -3.0", "gain -2.0"]
    assert first["head"] == first["nodes"][0]["id"]
    assert first["nodes"][0]["is_head"] is True
    assert first["nodes"][1]["side"] == "past"
    assert first["can_undo"] is True
    assert first["can_redo"] is False
    assert first["more"] is True
    cursor = first["nodes"][-1]["id"]
    second = client.get("/api/history", params={"limit": 2, "before": cursor}).json()
    assert second["nodes"][0]["label"] == "gain -1.0"
    assert {"id", "label", "created", "author", "is_marker", "op", "parent",
            "side"} <= set(second["nodes"][0])
    assert second["nodes"][0]["op"] == "set_track"
    assert "context" not in second["nodes"][0]
    # the whole of it eventually ends
    before = second["nodes"][-1]["id"]
    last = client.get("/api/history", params={"limit": 50, "before": before}).json()
    assert last["more"] is False


def test_history_page_marks_markers_and_the_redo_side(client, session, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    session.history.session_closed()
    client.post("/api/undo")
    page = client.get("/api/history", params={"limit": 10}).json()
    marker = page["nodes"][0]
    assert marker["is_marker"] is True
    assert marker["marker"] == "closed"
    assert marker["side"] == "redo"
    assert page["can_redo"] is True


def test_history_page_limit_is_checked(client):
    r = client.get("/api/history", params={"limit": 0})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.server.bad_request"
    r = client.get("/api/history", params={"limit": 100000})
    assert r.status_code == 400


def test_history_without_a_limit_still_lists_everything(client, loaded):
    body = client.get("/api/history").json()
    assert body["nodes"][0]["label"] == "new project"


def test_undo_across_a_marker_says_which_step_and_which_marker(client, session, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    session.history.session_closed()
    session.history.session_opened()
    undone = client.post("/api/undo").json()
    assert undone["moved"]["direction"] == "undo"
    assert undone["moved"]["step"]["label"] == "quieter"
    assert undone["moved"]["step"]["created"]
    assert undone["moved"]["crossed_marker"] is True
    redone = client.post("/api/redo").json()
    assert redone["moved"]["direction"] == "redo"
    # the markers lie after the step, so redoing it passes none
    assert redone["moved"]["crossed_marker"] is False


def test_undo_without_a_marker_does_not_claim_one(client, loaded):
    track = loaded["project"]["tracks"][0]["id"]
    client.post("/api/edit", json={"op": "set_track", "label": "quieter",
                                   "args": {"track_id": track, "gain_db": -6.0}})
    undone = client.post("/api/undo").json()
    assert undone["moved"]["crossed_marker"] is False
    assert undone["moved"]["step"]["label"] == "quieter"


def test_nothing_to_undo_reports_no_move(client):
    assert client.post("/api/undo").json()["moved"] is None


# -- the view memory (WP35) ---------------------------------------------------

def test_view_memory_round_trip_does_not_touch_the_project(client, session):
    before = client.get("/api/state").json()
    assert client.get("/api/view-memory").json() == {"view": None}
    r = client.put("/api/view-memory", json={"view": {"zoom": 3.5, "future": [1]}})
    assert r.status_code == 200
    assert client.get("/api/view-memory").json() == {"view": {"zoom": 3.5, "future": [1]}}
    after = client.get("/api/state").json()
    assert after["head"] == before["head"]
    assert after["can_undo"] == before["can_undo"]


def test_view_memory_is_keyed_by_the_project(client, session):
    client.put("/api/view-memory", json={"view": {"zoom": 1}})
    assert ViewMemory().get(session.package.manifest["id"]) == {"zoom": 1}


@pytest.mark.parametrize("body", [{"view": 5}, {"view": [1]}, {},
                                  {"view": {"a": "x" * 40_000}}])
def test_view_memory_junk_is_a_translated_400(client, body):
    r = client.put("/api/view-memory", json=body)
    assert r.status_code == 400
    assert r.json()["error"]["text"]
