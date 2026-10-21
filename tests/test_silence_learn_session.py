"""Calculate Auto-Silence values from the selection, through the session and the API:
one job (measure if needed, then learn), nothing committed, refusals explained."""

import pytest
from fastapi.testclient import TestClient
from test_silence_session import RATE, burst_wav, wait_job

from kuulas import analysis
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def muted_start(session, tmp_path):
    """One speaker: room noise for 8 s, then talk with pauses. The first 7 s are
    split off and muted by hand. Returns ``(muted clip id, open clip id)``."""
    talk = [(8.0 + i, 8.6 + i) for i in range(10)]
    session.import_media([str(burst_wav(tmp_path / "a.wav", talk, 20.0, seed=3))])
    clip = session.state.tracks[0].clips[0].id
    session.edit("split_clip", {"clip_id": clip, "at": 7 * RATE, "new_id": "rest"})
    session.edit("set_clip", {"clip_id": clip, "muted": True})
    return clip, "rest"


def learned(session, args):
    out = session.silence_learn(args)
    job = wait_job(session, out["jobs"][0])
    assert job["state"] == "completed", job
    return job


def test_the_job_learns_the_options_and_commits_nothing(session, tmp_path):
    muted, rest = muted_start(session, tmp_path)
    steps = len(session.history.nodes())
    state = session.state
    job = learned(session, {"clip_ids": [muted, rest], "dominance_db": 9})
    assert job["kind"] == "silence_learn"
    result = job["result"]
    assert result["learned"] is True
    assert result["tracks"][0]["code"] == "learned"
    assert result["tracks"][0]["muted_seconds"] == pytest.approx(7.0)
    assert result["options"]["dominance_db"] == 9
    assert result["key"] == analysis.silence_key(state)
    assert session.state is state
    assert len(session.history.nodes()) == steps
    # The panel opens on it at once: the measure is already there.
    assert session.silence_measure()["ready"] is True


def test_too_little_muted_audio_is_refused_with_its_reason(session, tmp_path):
    muted, rest = muted_start(session, tmp_path)
    session.edit("split_clip", {"clip_id": muted, "at": 2 * RATE, "new_id": "late"})
    result = learned(session, {"clip_ids": [muted, rest]})["result"]
    assert result["learned"] is False
    assert result["tracks"][0]["code"] == "too_little"


def test_a_selection_without_speech_clips_is_refused_at_once(session, tmp_path):
    muted_start(session, tmp_path)
    with pytest.raises(EditError) as e:
        session.silence_learn({"clip_ids": ["nope"]})
    assert e.value.key == "error.silence.learn_no_selection"


def test_the_route_queues_the_job(session, tmp_path):
    muted, rest = muted_start(session, tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, None, language="en", ui_dir=ui)) as client:
        r = client.post("/api/silence/learn", json={"clip_ids": [muted, rest]})
        assert r.status_code == 202, r.text
        job = wait_job(session, r.json()["jobs"][0])
        assert job["result"]["learned"] is True
        bad = client.post("/api/silence/learn", json={"clip_ids": []})
        assert bad.status_code == 400
        assert bad.json()["error"]["key"] == "error.silence.learn_no_selection"
