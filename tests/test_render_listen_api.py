"""POST /api/render-listen and the ``render`` part of the project state: switching
between the edit and the rendered mix, refused with a translated error when there is no
render or it no longer matches the edit. A fake engine; no audio device."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import export, messages
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class ListenEngine:
    """The parts of the engine the route uses; ``keep`` is called on changes as the
    real engine's ``set_project`` does."""

    def __init__(self, session):
        self.source = None
        self.keep = None
        session.subscribe(self.changed)

    def changed(self, project):
        if self.keep is not None and not self.keep(project):
            self.clear_listen_source()

    @property
    def listening(self):
        return self.source is not None

    def set_listen_source(self, project, sources, keep=None):
        self.source = (project, sources)
        self.keep = keep

    def clear_listen_source(self, **_kwargs):
        self.source = None
        self.keep = None

    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": [],
                "listen": self.listening}

    def stop(self):
        pass


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    rng = np.random.default_rng(1)
    sf.write(src / "Olli.wav", (rng.standard_normal(2 * RATE) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    s.import_media([str(src / "Olli.wav")])
    yield s
    s.close()


@pytest.fixture
def client(session, tmp_path):
    engine = ListenEngine(session)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, engine, language="en", ui_dir=ui)) as c:
        c.engine = engine
        yield c


def note(session, tmp_path, rng=None) -> Path:
    path = tmp_path / "mix.wav"
    sf.write(path, np.zeros((RATE, 2), dtype=np.float32), RATE, subtype="PCM_24")
    session.note_render({"path": str(path), "name": path.name, "range": rng,
                         "edit_key": export.audio_key(session.state), "frames": RATE,
                         "rate": RATE})
    return path


def test_no_render_is_refused_with_a_translated_error(client):
    r = client.post("/api/render-listen", json={"on": True})
    assert r.status_code == 409
    assert r.json()["error"]["key"] == "error.render_listen.none"
    assert "no rendered mix" in r.json()["error"]["text"]
    state = client.get("/api/state").json()
    assert state["render"]["available"] is False
    assert state["render"]["listening"] is False


def test_switching_on_and_off(client, session, tmp_path):
    note(session, tmp_path, rng=[RATE // 2, RATE])
    r = client.post("/api/render-listen", json={"on": True})
    assert r.status_code == 200
    render = r.json()["render"]
    assert render == {**render, "available": True, "current": True, "listening": True,
                      "name": "mix.wav", "range": [RATE // 2, RATE]}
    project, sources = client.engine.source
    [clip] = project.tracks[0].clips
    assert clip.start == RATE // 2  # a range render plays at its place on the timeline
    assert set(sources) == {clip.media}
    r = client.post("/api/render-listen", json={"on": False})
    assert r.status_code == 200
    assert r.json()["render"]["listening"] is False
    assert client.engine.source is None


def test_a_stale_render_is_refused_and_an_edit_ends_listening(client, session, tmp_path):
    note(session, tmp_path)
    assert client.post("/api/render-listen", json={"on": True}).status_code == 200
    track = session.state.tracks[0]
    r = client.post("/api/edit", json={"op": "set_track",
                                       "args": {"track_id": track.id, "gain_db": -3.0}})
    render = r.json()["render"]
    assert render["listening"] is False
    assert render["current"] is False
    assert render["available"] is True  # the older render is still remembered
    r = client.post("/api/render-listen", json={"on": True})
    assert r.status_code == 409
    assert r.json()["error"]["key"] == "error.render_listen.stale"


def test_a_missing_file_is_refused(client, session, tmp_path):
    note(session, tmp_path).unlink()
    r = client.post("/api/render-listen", json={"on": True})
    assert r.status_code == 409
    assert r.json()["error"]["key"] == "error.render_listen.missing"
    assert client.get("/api/state").json()["render"]["missing"] is True


def test_a_bad_body_is_a_400(client):
    r = client.post("/api/render-listen", json={"on": "yes"})
    assert r.status_code == 400
