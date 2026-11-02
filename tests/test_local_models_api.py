"""Model setup is available to the GUI without touching project content."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import local_models
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture
def api(tmp_path, monkeypatch):
    receipt = tmp_path / "cache" / "installation.json"
    monkeypatch.setenv("ORUKEET_INSTALLATION", str(receipt))
    session = Session(tmp_path / "Empty.kuulas")
    try:
        with TestClient(create_app(session, FakeEngine())) as client:
            yield client, session, tmp_path
    finally:
        session.close()


def test_gui_readiness_detects_deleted_files_from_a_valid_receipt(api):
    client, session, root = api
    before = session.history.head
    response = client.get("/api/transcribe/local-model")
    assert response.status_code == 200
    assert not response.json()["ready"]
    model, runtime = root / "model.bin", root / "runtime"
    model.write_bytes(b"weights")
    runtime.mkdir()
    receipt = Path(response.json()["receipt"])
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({"model": str(model), "runtime": str(runtime),
                                   "device": "cpu"}))
    assert client.get("/api/transcribe/local-model").json()["ready"]
    model.unlink()
    assert not client.get("/api/transcribe/local-model").json()["ready"]
    assert session.history.head == before


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
