"""The export dialog's choices reach the engine: the in/out range, some tracks only,
a loudness target, a chosen name, and the mute/solo rule reported for a mix."""

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


def voice(path: Path, seconds: float, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    audio = (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(voice(src / "Olli.wav", 6, 1)),
                    str(voice(src / "Maija.wav", 6, 2)),
                    str(voice(src / "Ville.wav", 4, 3))])
    yield s
    s.close()


class _Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def client_for(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir(exist_ok=True)
    return TestClient(create_app(session, _Engine(), language="en", ui_dir=ui))


def wait(session, job_id, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError(session.jobs.list())


def done(session, job_id):
    job = wait(session, job_id)
    assert job["state"] == "completed", job
    return job["result"]


def test_a_mix_of_the_in_out_range_is_only_that_long(session, tmp_path):
    result = done(session, session.export_mix(
        {"folder": str(tmp_path / "o"), "range": [RATE, 3 * RATE]})[0])
    assert sf.info(result["path"]).frames == 2 * RATE
    assert "0m01s" in Path(result["path"]).name  # the range is in the name
    assert result["settings"]["range"] == [RATE, 3 * RATE]


def test_a_whole_mix_has_no_range_in_its_name(session, tmp_path):
    result = done(session, session.export_mix({"folder": str(tmp_path / "o")})[0])
    assert sf.info(result["path"]).frames == session.state.length
    assert "\N{EN DASH}" not in Path(result["path"]).name


def test_a_chosen_name_never_overwrites_an_existing_file(session, tmp_path):
    args = {"folder": str(tmp_path / "o"), "name": "Cut for Maija"}
    first = done(session, session.export_mix(args)[0])
    assert Path(first["path"]).name == "Cut for Maija v1.wav"
    before = Path(first["path"]).read_bytes()
    session.edit("set_track", {"track_id": session.state.tracks[0].id, "gain_db": -6.0})
    second = done(session, session.export_mix(args)[0])
    assert Path(second["path"]).name == "Cut for Maija v2.wav"
    assert Path(first["path"]).read_bytes() == before


def test_a_name_with_braces_is_taken_literally(session, tmp_path):
    result = done(session, session.export_mix(
        {"folder": str(tmp_path / "o"), "name": "a {b} c"})[0])
    assert Path(result["path"]).name == "a {b} c v1.wav"


def test_only_the_chosen_tracks_are_written(session, tmp_path):
    olli, maija, _ville = session.state.tracks
    result = done(session, session.export_tracks(
        {"folder": str(tmp_path / "o"), "track_ids": [olli.id, maija.id]})[0])
    names = sorted(Path(p).name for p in result["paths"])
    assert len(names) == 2
    assert all("Ville" not in n for n in names)
    assert result["track_count"] == 2


def test_chosen_tracks_in_a_range(session, tmp_path):
    olli = session.state.tracks[0]
    result = done(session, session.export_tracks(
        {"folder": str(tmp_path / "o"), "track_ids": [olli.id], "range": [0, RATE]})[0])
    assert sf.info(result["paths"][0]).frames == RATE


def test_an_unknown_or_empty_track_choice_is_refused(session, tmp_path):
    with pytest.raises(messages.KuulasError) as e:
        session.export_tracks({"folder": str(tmp_path / "o"), "track_ids": ["nope"]})
    assert e.value.key == "error.export.bad_tracks"
    with pytest.raises(messages.KuulasError) as e:
        session.export_tracks({"folder": str(tmp_path / "o"), "track_ids": []})
    assert e.value.key == "error.export.bad_tracks"


def test_the_route_answers_400_for_bad_tracks(session, tmp_path):
    client = client_for(session, tmp_path)
    response = client.post("/api/export-tracks", json={"track_ids": ["nope"]})
    assert response.status_code == 400


def test_a_loudness_target_and_bitrate_reach_the_mix(session, tmp_path):
    result = done(session, session.export_mix(
        {"folder": str(tmp_path / "o"), "master_lufs": -16.0, "format": "mp3",
         "kbps": 160})[0])
    assert result["settings"]["master_lufs"] == -16.0
    assert result["settings"]["mp3_kbps"] == 160
    assert result["master"] is not None


def test_a_mix_says_which_tracks_came_out_as_silence(session, tmp_path):
    ville = session.state.tracks[2]
    session.edit("set_track", {"track_id": ville.id, "mute": True})
    result = done(session, session.export_mix({"folder": str(tmp_path / "o")})[0])
    assert result["silent"] == ["Ville"]


def test_a_loudness_target_set_to_off_clears_the_remembered_one(session, tmp_path):
    folder = str(tmp_path / "o")
    done(session, session.export_mix({"folder": folder, "master_lufs": -16.0})[0])
    assert session.export_settings()["mix"]["master_lufs"] == -16.0
    done(session, session.export_mix({"folder": folder, "master_lufs": None})[0])
    assert session.export_settings()["mix"]["master_lufs"] is None
    # and a later export that says nothing about it stays unmastered
    result = done(session, session.export_mix({"folder": folder})[0])
    assert result["master"] is None


def test_the_remembered_settings_route(session, tmp_path):
    done(session, session.export_mix(
        {"folder": str(tmp_path / "o"), "format": "flac"})[0])
    got = client_for(session, tmp_path).get("/api/export-settings").json()
    assert got["mix"]["format"] == "flac"
    assert got["tracks"] is None
    assert got["edit"]
    assert got["project"] == str(session.package.path)
    assert got["folder"].endswith("o")
