"""Session.transcript_text and GET /api/transcript-text."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages
from kuulas import transcript_text as tt
from kuulas.clock import FLICKS
from kuulas.server import create_app
from kuulas.session import Session, TranscriptTextError

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class FakeEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


def words(*spans):
    return [{"w": w, "s": round(s * FLICKS), "e": round(e * FLICKS), "spk": spk}
            for w, s, e, spk in spans]


@pytest.fixture
def session(tmp_path: Path):
    s = Session(tmp_path / "Text.kuulas")
    wav = tmp_path / "a.wav"
    rng = np.random.default_rng(1)
    sf.write(wav, (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    s.import_media([str(wav)])
    s.set_transcript(s.state.media[0].id,
                     words(("hello", 0.1, 0.5, "A"), ("world", 0.6, 1.0, "A")), "t")
    yield s
    s.close()


def client(session, tmp_path, language="en"):
    ui = tmp_path / "ui"
    ui.mkdir(exist_ok=True)
    return TestClient(create_app(session, FakeEngine(), language=language, ui_dir=ui))


def test_txt(session):
    text = session.transcript_text("txt")
    assert "hello world" in text
    assert text == tt.to_text(tt.paragraphs(
        __import__("kuulas.transcript", fromlist=["x"]).timeline_words(
            session.state, session.transcripts()), rate=session.state.rate))


def test_md(session):
    text = session.transcript_text("md")
    assert "hello world" in text
    assert "**A**" in text


def test_bad_format_raises(session):
    with pytest.raises(TranscriptTextError) as e:
        session.transcript_text("doc")
    assert e.value.key == "error.transcript_text.bad_format"


def test_lock_free_while_building(session, monkeypatch):
    free = []
    real = tt.paragraphs

    def probe(*a, **k):
        def try_lock():
            got = session.lock.acquire(timeout=1.0)
            if got:
                session.lock.release()
            free.append(got)
        th = threading.Thread(target=try_lock)
        th.start()
        th.join()
        return real(*a, **k)

    monkeypatch.setattr(tt, "paragraphs", probe)
    session.transcript_text("txt")
    assert free == [True]


def test_api_txt(session, tmp_path):
    r = client(session, tmp_path).get("/api/transcript-text?format=txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"] == 'attachment; filename="transcript.txt"'
    assert "hello world" in r.text


def test_api_md(session, tmp_path):
    r = client(session, tmp_path).get("/api/transcript-text?format=md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"] == 'attachment; filename="transcript.md"'


@pytest.mark.parametrize(("lang", "needle"), [
    ("en", "Unknown transcript format: doc. Use txt or md."),
    ("fi", "Tuntematon litteraattimuoto: doc. Käytä txt tai md."),
])
def test_api_bad_format(session, tmp_path, lang, needle):
    r = client(session, tmp_path, lang).get("/api/transcript-text?format=doc")
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["key"] == "error.transcript_text.bad_format"
    assert needle in err["text"]
