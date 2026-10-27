"""Model setup is available to the GUI without touching project content."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import local_models
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_ORUKEET_FILE", str(tmp_path / "orukeet.json"))
    monkeypatch.setattr(local_models, "config_dir", lambda: tmp_path / "config")
    session = Session(tmp_path / "Empty.kuulas")
    try:
        with TestClient(create_app(session, FakeEngine())) as client:
            yield client, session, tmp_path
    finally:
        session.close()


def test_gui_can_inspect_missing_model_and_select_existing_folder(api):
    client, session, root = api
    before = session.history.head
    response = client.get("/api/transcribe/local-model")
    assert response.status_code == 200
    folder = root / "converted"
    folder.mkdir()
    (folder / "config.json").write_text(json.dumps({"target": "EncDecRNNTBPEModel"}))
    (folder / "model.safetensors").write_bytes(b"test weights")
    chosen = client.post("/api/transcribe/local-model/select", json={"path": str(folder)})
    assert chosen.status_code == 200
    assert chosen.json()["ready"]
    assert session.history.head == before


def test_bad_model_is_an_actionable_gui_error(api):
    client, _, root = api
    response = client.post("/api/transcribe/local-model/select", json={"path": str(root)})
    assert response.status_code == 400
    assert response.json()["error"]["key"] == "error.orukeet.invalid_model"


def test_install_returns_a_progress_job_without_blocking_request(api, monkeypatch):
    client, session, _ = api
    before = session.history.head
    def install(progress):
        progress(0.5)
        return {"ready": True}
    monkeypatch.setattr(local_models, "install", install)
    response = client.post("/api/transcribe/local-model/install")
    assert response.status_code == 202
    job_id = response.json()["job"]
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        jobs = client.get("/api/jobs").json()["jobs"]
        found = next(j for j in jobs if j["id"] == job_id)
        if found["state"] == "completed":
            break
        time.sleep(0.01)
    assert found["state"] == "completed"
    assert found["progress"] == 1
    assert found["result"] == {"ready": True}
    assert session.history.head == before
