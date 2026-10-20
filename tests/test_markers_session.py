"""Chapter export and region batch export through the session and API (WP19h)."""

import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import messages
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    rng = np.random.default_rng(1)
    for name, seconds in (("a", 6), ("b", 4)):
        sf.write(src / f"{name}.wav",
                 (rng.standard_normal(seconds * RATE) * 0.1).astype(np.float32),
                 RATE, subtype="PCM_16")
    s = Session(tmp_path / "Talk.kuulas")
    s.import_media([str(src / "a.wav"), str(src / "b.wav")])
    yield s
    s.close()


class _NoEngine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, _NoEngine(), language="en", ui_dir=ui)) as c:
        yield c


def mark(session, mid, name, start, end=None, kind="marker"):
    args = {"marker_id": mid, "name": name, "start": start, "kind": kind}
    if end is not None:
        args["end"] = end
    session.edit("add_marker", args)


def wait(session, job_id, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


# -- chapters ------------------------------------------------------------------


def test_chapters_use_only_chapter_markers(session):
    mark(session, "a", "Intro", 0, kind="chapter")
    mark(session, "b", "Flag", RATE, kind="marker")
    mark(session, "c", "Topic", 65 * RATE, kind="chapter")
    mark(session, "d", "Part", 2 * RATE, 3 * RATE, kind="region")
    assert session.chapters("text") == "00:00:00 Intro\n00:01:05 Topic\n"
    data = json.loads(session.chapters("json"))
    assert [c["title"] for c in data["chapters"]] == ["Intro", "Topic"]


def test_chapters_follow_a_ripple_cut(session):
    mark(session, "a", "Intro", 0, kind="chapter")
    mark(session, "b", "Topic", 5 * RATE, kind="chapter")
    session.edit("ripple_delete", {"start": RATE, "end": 3 * RATE})
    assert session.chapters("text") == "00:00:00 Intro\n00:00:03 Topic\n"


def test_chapters_bad_style_is_refused(session):
    with pytest.raises(messages.KuulasError) as e:
        session.chapters("xml")
    assert e.value.key == "error.chapters.unknown_style"


def test_get_chapters_text_and_json_are_attachments(client, session):
    mark(session, "a", "Äiti", 0, kind="chapter")
    r = client.get("/api/chapters", params={"style": "text"})
    assert r.status_code == 200
    assert r.text == "00:00:00 Äiti\n"
    assert r.headers["content-disposition"] .startswith(
        'attachment; filename="Talk chapters.txt"')
    r = client.get("/api/chapters", params={"style": "json"})
    assert r.headers["content-disposition"] .startswith(
        'attachment; filename="Talk chapters.json"')
    assert r.json()["chapters"][0]["title"] == "Äiti"


def test_get_chapters_bad_style_is_a_translated_400(client):
    r = client.get("/api/chapters", params={"style": "xml"})
    assert r.status_code == 400
    assert "xml" in r.json()["error"]["text"]


def test_marker_edit_errors_are_400(client):
    r = client.post("/api/edit", json={"op": "delete_marker",
                                       "args": {"marker_id": "nope"}})
    assert r.status_code == 400


# -- regions batch export --------------------------------------------------------


def frames(path) -> int:
    return sf.info(path).frames


def test_each_region_is_its_own_file_of_the_right_length(session, tmp_path):
    mark(session, "r1", "Intro", RATE, 2 * RATE + 24000, kind="region")
    mark(session, "r2", "Main: part/2", 3 * RATE, 5 * RATE, kind="region")
    mark(session, "m", "Not a region", 0)
    out = tmp_path / "regions"
    [job_id] = session.export_regions({"folder": str(out), "format": "wav",
                                       "bit_depth": 16})
    job = wait(session, job_id)
    assert job["state"] == "completed", job
    files = sorted(p.name for p in out.iterdir())
    assert files == ["Talk - 01 Intro.wav", "Talk - 02 Main part2.wav"]
    assert frames(out / "Talk - 01 Intro.wav") == RATE + 24000
    assert frames(out / "Talk - 02 Main part2.wav") == 2 * RATE


def test_a_second_run_never_overwrites(session, tmp_path):
    mark(session, "r1", "Intro", RATE, 2 * RATE, kind="region")
    out = tmp_path / "regions"
    for _ in range(2):
        [job_id] = session.export_regions({"folder": str(out), "format": "wav"})
        assert wait(session, job_id)["state"] == "completed"
    assert sorted(p.name for p in out.iterdir()) == [
        "Talk - 01 Intro 2.wav", "Talk - 01 Intro.wav"]


def test_name_template_and_region_past_the_end_is_clamped(session, tmp_path):
    mark(session, "r1", "Tail", 5 * RATE, 99 * RATE, kind="region")
    out = tmp_path / "regions"
    [job_id] = session.export_regions({"folder": str(out), "format": "wav",
                                       "name_template": "{name} at {start}"})
    assert wait(session, job_id)["state"] == "completed"
    [path] = list(out.iterdir())
    assert path.name == "Tail at 00-00-05.wav"
    assert frames(path) == RATE


def test_no_regions_is_a_translated_error(session, tmp_path):
    mark(session, "m", "Only a flag", 0)
    with pytest.raises(messages.KuulasError) as e:
        session.export_regions({"folder": str(tmp_path / "x")})
    assert e.value.key == "error.regions.none"


def test_bad_template_fails_before_any_job(session, tmp_path):
    mark(session, "r1", "Intro", RATE, 2 * RATE, kind="region")
    with pytest.raises(messages.KuulasError) as e:
        session.export_regions({"folder": str(tmp_path / "x"), "name_template": "{oops}"})
    assert e.value.key == "error.regions.bad_template"


def test_post_export_regions_answers_with_one_job(client, session, tmp_path):
    mark(session, "r1", "Intro", RATE, 2 * RATE, kind="region")
    mark(session, "r2", "Two", 3 * RATE, 4 * RATE, kind="region")
    r = client.post("/api/export-regions", json={"folder": str(tmp_path / "o")})
    assert r.status_code == 200, r.text
    [job_id] = r.json()["jobs"]
    assert wait(session, job_id)["state"] == "completed"
    assert len(list(Path(tmp_path / "o").iterdir())) == 2


def test_post_export_regions_without_regions_is_a_400(client):
    r = client.post("/api/export-regions", json={})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.regions.none"
