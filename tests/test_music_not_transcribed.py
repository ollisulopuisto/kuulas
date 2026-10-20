"""Music-kind tracks are not transcribed: a recording is skipped when EVERY clip that
uses it is on a music track (docs/NO_MUSIC_TRANSCRIBE.md). Pure helper + session guard."""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import bgjobs, transcribable
from kuulas.messages import KuulasError
from kuulas.model import Clip, Media, Project, Track
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def clip(cid, media):
    return Clip(id=cid, media=media, start=0, offset=0, length=100)


def project(**tracks):
    return Project(
        media=(Media(id="m1", name="a.wav", channels=1, frames=100),
               Media(id="m2", name="b.wav", channels=1, frames=100)),
        tracks=tuple(Track(id=k, name=k, kind=kind,
                           clips=tuple(clip(f"c{k}{m}", m) for m in ms))
                     for k, (kind, ms) in tracks.items()))


def test_music_only_recording_is_not_transcribable():
    p = project(S=("speech", ["m1"]), M=("music", ["m2"]))
    assert transcribable.is_transcribable(p, "m1")
    assert not transcribable.is_transcribable(p, "m2")
    assert transcribable.music_only_ids(p) == {"m2"}


def test_recording_on_speech_and_music_is_transcribed():
    p = project(S=("speech", ["m1"]), M=("music", ["m1"]))
    assert transcribable.is_transcribable(p, "m1")


def test_unused_recording_is_transcribed():
    p = project(M=("music", ["m1"]))
    assert transcribable.is_transcribable(p, "m2")
    assert transcribable.music_only_ids(p) == {"m1"}


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def build(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    paths = []
    for i, name in enumerate(("Olli", "Maija")):
        audio = (np.random.default_rng(i).standard_normal(RATE) * 0.1).astype(np.float32)
        sf.write(src / f"{name}.wav", audio, RATE, subtype="PCM_16")
        paths.append(str(src / f"{name}.wav"))
    s.import_media(paths)
    return s


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(bgjobs, "launch_worker", lambda path: None)
    s = build(tmp_path)
    music = next(t for t in s.state.tracks if t.clips[0].media == s.state.media[1].id)
    s.edit("set_track", {"track_id": music.id, "kind": "music"})
    yield s
    s.close()


def test_session_refuses_music_only_media(session):
    music_id = session.state.media[1].id
    with pytest.raises(KuulasError) as err:
        session.transcribe([music_id])
    assert err.value.key == "error.transcribe.music_only"
    jobs = bgjobs.jobs_dir(session.package.path)
    assert not jobs.exists() or not list(jobs.iterdir())


def test_session_refuses_music_even_for_colab_and_mixed_batches(session):
    ids = [m.id for m in session.state.media]
    with pytest.raises(KuulasError):
        session.transcribe(ids, backend="colab")


def test_force_transcribes_music(session):
    ids = [m.id for m in session.state.media]
    (job_id,) = session.transcribe(ids, force=True)
    job = bgjobs.read_json(bgjobs.job_file(session.package.path, job_id))
    assert [i["id"] for i in job["items"]] == ids


def test_speech_media_still_transcribes(session):
    (job_id,) = session.transcribe([session.state.media[0].id])
    assert job_id


def test_endpoint_refuses_music_and_accepts_force(session):
    client = TestClient(create_app(session, Engine()))
    music_id = session.state.media[1].id
    r = client.post("/api/transcribe", json={"media_ids": [music_id]})
    assert r.status_code == 400
    assert r.json()["error"]["key"] == "error.transcribe.music_only"
    r = client.post("/api/transcribe", json={"media_ids": [music_id], "force": True})
    assert r.status_code == 202
