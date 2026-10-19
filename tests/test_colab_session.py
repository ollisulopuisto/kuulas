"""Transcribe on Colab (WP78): Media.timing, Session.transcribe(backend colab), the API.
The tool is a fake script; see test_colab_transcribe.py. No network."""

import json
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages
from kuulas.model import Media
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000

FAKE = textwrap.dedent('''
    import json, os, sys, time
    argv = sys.argv[1:]
    mode = os.environ.get("FAKE_MODE", "ok")
    audio = [argv[i + 1] for i, a in enumerate(argv) if a == "--audio"]
    folder = argv[argv.index("--json") + 1]
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv, "audio": audio}, f)
    print("PROGRESS 10 uploading", flush=True)
    if mode == "fail":
        print("no GPU left", flush=True)
        sys.exit(2)
    if mode == "hang":
        time.sleep(60)
    if mode == "slow":
        time.sleep(1.0)
    for path in audio:
        stem = os.path.splitext(os.path.basename(path))[0]
        timing = os.environ.get("FAKE_TIMING", "whisper")
        doc = {"version": 1, "timing": timing, "language": "fi",
               "words": [{"w": stem, "s": 0.25, "e": 0.5}]}
        with open(os.path.join(folder, stem + ".words.json"), "w") as f:
            json.dump(doc, f)
    print("PROGRESS 100 done", flush=True)
''')


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    paths = []
    for i, name in enumerate(("Olli", "Maija")):
        rng = np.random.default_rng(i)
        audio = (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32)
        sf.write(src / f"{name}.wav", audio, RATE, subtype="PCM_16")
        paths.append(str(src / f"{name}.wav"))
    s.import_media(paths)
    yield s
    s.close()


@pytest.fixture
def tool(tmp_path, monkeypatch):
    script = tmp_path / "fake_colab.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    settings = tmp_path / "config" / "colab.json"
    monkeypatch.setenv("KUULAS_COLAB_FILE", str(settings))
    settings.parent.mkdir()
    settings.write_text(json.dumps({"command": [sys.executable, str(script)]}))
    return settings


@pytest.fixture
def client(session, tmp_path):
    app = create_app(session, Engine(), language="en", ui_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def wait_job(client, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def ids(session):
    return [m.id for m in session.state.media]


def start(client, session, **body):
    body = {"media_ids": ids(session), "backend": "colab", **body}
    response = client.post("/api/transcribe", json=body)
    assert response.status_code == 202, response.text
    return response.json()["jobs"]


# -- Media.timing --------------------------------------------------------


def test_timing_is_written_only_when_set():
    plain = Media(id="m", name="a.wav", channels=1, frames=10)
    assert "timing" not in plain.to_dict()
    set_ = Media(id="m", name="a.wav", channels=1, frames=10, timing="ctc-v1")
    assert set_.to_dict()["timing"] == "ctc-v1"
    assert Media.from_dict(set_.to_dict()).timing == "ctc-v1"
    assert Media.from_dict(plain.to_dict()).timing == ""


def test_a_project_without_timing_keeps_its_material_bytes(session):
    assert "media_timing" not in session.history.material
    assert all("timing" not in m for m in session.state.to_dict()["media"])


# -- the job -------------------------------------------------------------


def test_colab_is_one_job_that_stores_words_and_timing(session, client, tool, tmp_path):
    jobs = start(client, session)
    assert len(jobs) == 1  # ONE job for the chosen recordings
    job = wait_job(client, jobs[0])
    assert job["state"] == "completed", job
    for media in session.state.media:
        words = session.transcripts()[media.id]
        assert [w["w"] for w in words] == [Path(media.name).stem]
        assert words[0]["s"] > 0  # flicks
        assert media.timing == "whisper"
    seen = json.loads((tmp_path / "call.json").read_text())
    assert len(seen["audio"]) == 2


def test_the_source_is_the_one_the_local_backend_uses(session, client, tool, tmp_path):
    wait_job(client, start(client, session)[0])
    seen = json.loads((tmp_path / "call.json").read_text())
    wanted = [str(session.store.transcription_path(i)) for i in ids(session)]
    assert seen["audio"] == wanted


def test_model_and_language_go_to_the_tool(session, client, tool, tmp_path):
    wait_job(client, start(client, session, model="small", language="fi")[0])
    argv = json.loads((tmp_path / "call.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "small"
    assert argv[argv.index("--language") + 1] == "fi"
    assert "--no-drive" not in argv  # the plain-audio mode never uses Drive: not asked


def test_ctc_timing_is_stored(session, client, tool, monkeypatch):
    monkeypatch.setenv("FAKE_TIMING", "ctc-v1")
    wait_job(client, start(client, session)[0])
    assert {m.timing for m in session.state.media} == {"ctc-v1"}


def test_undo_takes_the_transcript_and_its_timing_back(session, client, tool):
    wait_job(client, start(client, session)[0])
    session.undo()
    session.undo()
    assert session.transcripts() == {}
    assert {m.timing for m in session.state.media} == {""}
    assert "media_timing" not in session.history.material


def test_one_media_only(session, client, tool, tmp_path):
    first = ids(session)[0]
    wait_job(client, start(client, session, media_ids=[first])[0])
    assert list(session.transcripts()) == [first]
    assert len(json.loads((tmp_path / "call.json").read_text())["audio"]) == 1


def test_a_failed_run_stores_nothing_and_says_why(session, client, tool, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "fail")
    job = wait_job(client, start(client, session)[0])
    assert job["state"] == "failed"
    assert job["error"]["key"] == "error.colab.failed"
    assert "no GPU left" in job["error"]["text"]
    assert session.transcripts() == {}


def test_a_missing_tool_is_one_clear_error(session, client, tool):
    tool.write_text(json.dumps({"command": ["definitely-not-colab-xyz"]}))
    job = wait_job(client, start(client, session)[0])
    assert job["error"]["key"] == "error.colab.not_found"
    assert session.transcripts() == {}


def test_a_malformed_result_stores_nothing(session, client, tool, monkeypatch):
    monkeypatch.setenv("FAKE_TIMING", "magic")
    job = wait_job(client, start(client, session)[0])
    assert job["error"]["key"] == "error.colab.result_timing"
    assert session.transcripts() == {}
    assert {m.timing for m in session.state.media} == {""}


def test_cancel_stops_the_tool_and_stores_nothing(session, client, tool, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "hang")
    job_id = start(client, session)[0]
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job_id)
        if job["message"].endswith("uploading"):
            break
        time.sleep(0.02)
    assert job["message"].endswith("uploading")
    assert 0 < job["progress"] < 1  # the tool's PROGRESS line is the bar
    started = time.monotonic()
    client.delete(f"/api/jobs/{job_id}")
    job = wait_job(client, job_id, timeout=20)
    assert job["state"] == "cancelled"
    assert time.monotonic() - started < 20
    assert session.transcripts() == {}


def test_a_transcript_changed_meanwhile_is_kept(session, client, tool, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "slow")
    first = ids(session)[0]
    job_id = start(client, session)[0]
    session.set_transcript(first, [{"w": "mine", "s": 0, "e": 5, "spk": ""}], "manual")
    job = wait_job(client, job_id)
    assert job["state"] == "failed"
    assert job["error"]["key"] == "error.transcribe.changed"
    assert session.transcripts()[first][0]["w"] == "mine"
    # WP79: per media, not all or nothing (the owner's choice: a result is added
    # automatically; only the one that would overwrite newer text is kept back).
    assert list(session.transcripts()) == ids(session)
    other = session.state.media[1]
    assert session.transcripts()[other.id][0]["w"] == Path(other.name).stem


def test_unknown_backend_and_media_are_refused(session, client, tool):
    r = client.post("/api/transcribe", json={"media_ids": ids(session), "backend": "x"})
    assert r.status_code == 400
    r = client.post("/api/transcribe", json={"media_ids": ["nope"], "backend": "colab"})
    assert r.status_code == 404


def test_local_transcription_still_works_and_clears_timing(session, client, tool,
                                                           monkeypatch):
    wait_job(client, start(client, session)[0])
    first = ids(session)[0]

    def fake_local(path, model="small", language=None, progress=None, **kwargs):
        return [{"w": "local", "s": 0, "e": 100, "spk": ""}]

    monkeypatch.setattr("kuulas.transcribe.local", fake_local)
    r = client.post("/api/transcribe", json={"media_ids": [first]})
    wait_job(client, r.json()["jobs"][0])
    by_id = {m.id: m for m in session.state.media}
    assert by_id[first].timing == ""  # a different engine: the marker no longer applies
    assert by_id[ids(session)[1]].timing == "whisper"


def test_correcting_a_word_keeps_the_timing(session, client, tool):
    wait_job(client, start(client, session)[0])
    first = ids(session)[0]
    session.correct_word(first, 0, "fixed")
    assert {m.id: m.timing for m in session.state.media}[first] == "whisper"


# -- the settings --------------------------------------------------------


def test_settings_endpoints(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_COLAB_FILE", str(tmp_path / "colab.json"))
    got = client.get("/api/settings/colab").json()
    assert got["settings"] == {}
    assert got["resolved"]["command"][0] == "uvx"
    assert got["resolved"]["no_drive"] is False
    put = client.put("/api/settings/colab", json={
        "command": ["colab-transcribe"], "cwd": "/x", "extra_args": ["--a"],
        "no_drive": True})
    assert put.status_code == 200
    again = client.get("/api/settings/colab").json()
    assert again["settings"]["cwd"] == "/x"
    assert again["resolved"]["no_drive"] is True
    bad = client.put("/api/settings/colab", json={"command": "uvx"})
    assert bad.status_code == 400
    assert bad.json()["error"]["key"] == "error.colab.bad_settings"


def test_read_only_project_refuses(session, client, tool, monkeypatch):
    monkeypatch.setattr(type(session), "read_only", property(lambda self: True))
    body = {"media_ids": ids(session), "backend": "colab"}
    r = client.post("/api/transcribe", json=body)
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.history.read_only"
