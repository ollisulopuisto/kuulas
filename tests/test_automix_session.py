"""Mix with the automixer (WP68 step 2): settings file, Session.automix, the API.
The automixer is a fake script; see test_automix.py."""

import json
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import automix, messages
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000

FAKE = textwrap.dedent('''
    import json, os, sys, time
    import numpy as np, soundfile as sf
    argv = sys.argv[1:]
    mode = argv[argv.index("--mode") + 1] if "--mode" in argv else "ok"
    out = argv[argv.index("-o") + 1]
    with open(os.environ["FAKE_LOG"], "w") as f:
        json.dump({"argv": argv}, f)
    print("loading", flush=True)
    if mode == "fail":
        print("boom", flush=True)
        sys.exit(3)
    if mode == "nothing":
        print("No tracks found", flush=True)
        sys.exit(0)
    if mode == "hang":
        print("working", flush=True)
        time.sleep(60)
    sf.write(out, np.zeros(4800, dtype="float32"), 48000)
    print("done", flush=True)
''')


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
def fake(tmp_path, monkeypatch):
    script = tmp_path / "fake_automixer.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "call.json"))
    return {"command": [sys.executable, str(script)], "cwd": str(tmp_path),
            "extra_args": []}


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "config" / "automixer.json"
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(path))
    return path


def wait_job(session, job_id, state="completed", timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            assert job["state"] == state, job
            return job
        time.sleep(0.02)
    raise AssertionError(session.jobs.list())


def test_settings_round_trip(settings_file):
    assert automix.load_settings() == {}
    automix.save_settings({"command": ["automixer"], "cwd": "", "extra_args": ["-v"]})
    assert automix.load_settings() == {"command": ["automixer"], "cwd": "",
                                       "extra_args": ["-v"]}


def test_damaged_settings_file_reads_as_empty(settings_file):
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("{nope", encoding="utf-8")
    assert automix.load_settings() == {}


@pytest.mark.parametrize("bad", [{"command": "automixer"}, {"command": []},
                                 {"command": [1]}, {"extra_args": "x"}, {"cwd": 5}])
def test_bad_settings_are_refused(settings_file, bad):
    with pytest.raises(automix.AutomixError) as e:
        automix.save_settings(bad)
    assert e.value.key == "error.automix.bad_settings"
    assert not settings_file.exists()


def test_session_automix_job_writes_the_mix(session, fake, settings_file, tmp_path):
    automix.save_settings(fake)
    [job_id] = session.automix({"target_lufs": -18})
    job = wait_job(session, job_id)
    assert Path(job["result"]["path"]).is_file()
    assert job["kind"] == "automix"
    argv = json.loads((tmp_path / "call.json").read_text())["argv"]
    assert "-18" in argv
    assert session.last_export_folder == str(Path(job["result"]["path"]).parent)


def test_session_automix_bad_params_fail_now(session, settings_file):
    with pytest.raises(automix.AutomixError):
        session.automix({"target_lufs": "loud"})


def test_session_automix_failure_shows_in_the_job(session, fake, settings_file):
    automix.save_settings({**fake, "extra_args": ["--mode", "fail"]})
    [job_id] = session.automix({})
    job = wait_job(session, job_id, "failed")
    assert job["error"]["key"] == "error.automix.failed"


def test_job_shows_the_last_log_line_and_is_indeterminate(session, fake, settings_file):
    automix.save_settings({**fake, "extra_args": ["--mode", "hang"]})
    [job_id] = session.automix({})
    deadline = time.monotonic() + 30
    job = {}
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job.get("message") == "working":
            break
        time.sleep(0.02)
    assert job["message"] == "working"
    assert job["indeterminate"] is True
    session.jobs.cancel(job_id)
    wait_job(session, job_id, "cancelled")


def test_exit_zero_without_output_is_no_output(session, fake, settings_file):
    automix.save_settings({**fake, "extra_args": ["--mode", "nothing"]})
    [job_id] = session.automix({})
    job = wait_job(session, job_id, "failed")
    assert job["error"]["key"] == "error.automix.no_output"


def test_stems_are_48k_and_equal_length(session, tmp_path):
    out = tmp_path / "probe"
    done = automix.export.run(session, session.tracks_export_args({"folder": str(out)}))
    data = json.loads((Path(done["path"]) / "tracks.json").read_text("utf-8"))
    infos = [sf.info(Path(done["path"]) / t["file"]) for t in data["tracks"]]
    assert {i.samplerate for i in infos} == {48000}
    assert len({i.frames for i in infos}) == 1


class IdleEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def test_automixer_settings_api(session, tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        r = c.get("/api/settings/automixer")
        assert r.status_code == 200
        assert r.json()["settings"] == {}
        assert r.json()["resolved"]["command"] == ["uv", "run", "automixer"]
        r = c.put("/api/settings/automixer",
                  json={"command": ["automixer"], "extra_args": ["-v"]})
        assert r.status_code == 200
        assert c.get("/api/settings/automixer").json()["settings"]["command"] == [
            "automixer"]
        r = c.put("/api/settings/automixer", json={"command": "automixer"})
        assert r.status_code == 400
        assert r.json()["key"] == "error.automix.bad_settings"
        r = c.post("/api/automix", json={"target_lufs": "loud"})
        assert r.status_code == 400
        assert r.json()["key"] == "error.automix.bad_target_lufs"
