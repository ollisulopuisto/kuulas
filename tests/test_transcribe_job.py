import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas.server import create_app
from kuulas.session import Session


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def wav(path: Path) -> Path:
    sf.write(path, np.zeros(4800, dtype=np.float32), 48000, subtype="PCM_16")
    return path


def wait_job(client, job_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()["jobs"]
        job = next(item for item in jobs if item["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("transcription job did not finish")


def test_local_transcription_job_commits_words_once(tmp_path, monkeypatch):
    session = Session(tmp_path / "Speech.kuulas")
    source = wav(tmp_path / "speech.wav")
    session.import_media([source])
    media_id = session.state.media[0].id
    calls = []

    def fake_local(path, model="small", language=None, progress=None, **kwargs):
        calls.append((path, model, language, kwargs))
        progress(1.0)
        return [{"w": "hello", "s": 0, "e": 100, "spk": ""}]

    monkeypatch.setattr("kuulas.session.transcribe.local", fake_local)
    try:
        app = create_app(session, Engine(), language="en", ui_dir=tmp_path)
        with TestClient(app) as client:
            response = client.post("/api/transcribe", json={"media_ids": [media_id]})
            assert response.status_code == 202, response.text
            job = wait_job(client, response.json()["jobs"][0])
            assert job["state"] == "completed"
            assert session.transcripts()[media_id][0]["w"] == "hello"
            assert calls[0][1:3] == ("small", None)
    finally:
        session.close()


def test_transcription_rejects_unknown_media(tmp_path):
    session = Session(tmp_path / "Speech.kuulas")
    try:
        app = create_app(session, Engine(), language="en", ui_dir=tmp_path)
        with TestClient(app) as client:
            response = client.post("/api/transcribe", json={"media_ids": ["missing"]})
        assert response.status_code == 404
    finally:
        session.close()


def test_transcription_does_not_replace_words_added_while_job_runs(tmp_path, monkeypatch):
    session = Session(tmp_path / "Speech.kuulas")
    session.import_media([wav(tmp_path / "speech.wav")])
    media_id = session.state.media[0].id
    started, finish = threading.Event(), threading.Event()

    def slow_local(*_args, **_kwargs):
        started.set()
        assert finish.wait(2)
        return [{"w": "stale", "s": 0, "e": 100, "spk": ""}]

    monkeypatch.setattr("kuulas.session.transcribe.local", slow_local)
    try:
        app = create_app(session, Engine(), language="en", ui_dir=tmp_path)
        with TestClient(app) as client:
            response = client.post("/api/transcribe", json={"media_ids": [media_id]})
            assert response.status_code == 202
            assert started.wait(1)
            session.set_transcript(media_id,
                                   [{"w": "new", "s": 0, "e": 100, "spk": ""}],
                                   "manual")
            finish.set()
            job = wait_job(client, response.json()["jobs"][0])
            assert job["state"] == "failed"
            assert job["error"]["key"] == "error.transcribe.changed"
            assert session.transcripts()[media_id][0]["w"] == "new"
    finally:
        finish.set()
        session.close()
