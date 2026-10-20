"""Tests for Session.subtitles method and GET /api/subtitles endpoint."""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages
from kuulas import subtitles as subtitles_mod
from kuulas.clock import FLICKS
from kuulas.server import create_app
from kuulas.session import Session, SubtitlesError

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


class FakeEngine:
    """Minimal engine mock for server tests."""

    def __init__(self):
        self.position = 0
        self.playing = False
        self.until = None
        self.notices: list[dict] = []

    def status(self):
        return {
            "playing": self.playing,
            "position": self.position,
            "until": self.until,
            "notices": list(self.notices),
        }

    def close(self):
        pass


def make_wav(path: Path, seconds: float = 2.0, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(
        path,
        (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
        RATE,
        subtype="PCM_16",
    )
    return path


def words(*spans):
    """(text, start_s, end_s, speaker) -> stored words in flicks."""
    return [
        {
            "w": w,
            "s": round(s * FLICKS),
            "e": round(e * FLICKS),
            "spk": spk,
        }
        for w, s, e, spk in spans
    ]


@pytest.fixture
def two_track_session(tmp_path: Path):
    s = Session(tmp_path / "Subtitles.kuulas")
    f_a = make_wav(tmp_path / "a.wav", seconds=2.0, seed=1)
    f_b = make_wav(tmp_path / "b.wav", seconds=2.0, seed=2)
    s.import_media([str(f_a), str(f_b)], track_per_file=True)
    m0 = s.state.media[0].id
    m1 = s.state.media[1].id
    s.set_transcript(
        m0,
        words(("hello", 0.1, 0.5, "A"), ("world", 0.6, 1.0, "A")),
        "t_a",
    )
    s.set_transcript(
        m1,
        words(("hi", 0.2, 0.4, "B"), ("there", 1.2, 1.6, "B")),
        "t_b",
    )
    yield s
    s.close()


def test_session_subtitles_srt(two_track_session: Session):
    s = two_track_session
    text = s.subtitles("srt")
    assert "00:00:00,100 -->" in text
    assert "hello" in text
    assert "A: " in text
    assert "B: " in text


def test_session_subtitles_vtt(two_track_session: Session):
    s = two_track_session
    text = s.subtitles("vtt")
    assert text.startswith("WEBVTT\n")
    assert "00:00:00.100 -->" in text
    assert "<v A>" in text
    assert "<v B>" in text


def test_session_subtitles_bad_format_raises(two_track_session: Session):
    s = two_track_session
    with pytest.raises(SubtitlesError) as exc_info:
        s.subtitles("doc")
    assert exc_info.value.key == "error.subtitles.bad_format"


def test_session_subtitles_does_not_hold_lock_while_building(
    two_track_session: Session, monkeypatch
):
    s = two_track_session
    free = []
    real_cues = subtitles_mod.cues

    def cues_with_probe(*args, **kwargs):
        def try_lock():
            got = s.lock.acquire(timeout=1.0)
            if got:
                s.lock.release()
            free.append(got)

        other = threading.Thread(target=try_lock)
        other.start()
        other.join()
        return real_cues(*args, **kwargs)

    monkeypatch.setattr(subtitles_mod, "cues", cues_with_probe)
    s.subtitles("srt")
    assert free == [True]


def test_session_subtitles_leaves_project_and_history_unchanged(
    two_track_session: Session,
):
    s = two_track_session
    head_before = s.history.head
    state_before = s.history.state

    s.subtitles("srt")
    s.subtitles("vtt")

    assert s.history.head == head_before
    assert s.history.state == state_before


def test_api_get_subtitles_srt(two_track_session: Session, tmp_path: Path):
    s = two_track_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.get("/api/subtitles?format=srt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-subrip")
    assert resp.headers["content-disposition"] .startswith(
        'attachment; filename="Subtitles subtitles.srt"')
    assert "00:00:00,100 -->" in resp.text
    assert "hello" in resp.text


def test_api_get_subtitles_vtt(two_track_session: Session, tmp_path: Path):
    s = two_track_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.get("/api/subtitles?format=vtt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/vtt")
    assert resp.headers["content-disposition"] .startswith(
        'attachment; filename="Subtitles subtitles.vtt"')
    assert resp.text.startswith("WEBVTT\n")
    assert "<v A>" in resp.text


def test_api_get_subtitles_bad_format_returns_400_en(
    two_track_session: Session, tmp_path: Path
):
    s = two_track_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="en", ui_dir=ui)
    client = TestClient(app)

    resp = client.get("/api/subtitles?format=doc")
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["key"] == "error.subtitles.bad_format"
    assert "Unknown subtitle format: doc. Use srt or vtt." in err["text"]


def test_api_get_subtitles_bad_format_returns_400_fi(
    two_track_session: Session, tmp_path: Path
):
    s = two_track_session
    engine = FakeEngine()
    ui = tmp_path / "ui"
    ui.mkdir()
    app = create_app(s, engine, language="fi", ui_dir=ui)
    client = TestClient(app)

    resp = client.get("/api/subtitles?format=doc")
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["key"] == "error.subtitles.bad_format"
    assert "Tuntematon tekstitysmuoto: doc. Käytä srt tai vtt." in err["text"]
