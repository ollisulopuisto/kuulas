"""Auto-Silence through the session: options, the preview job, Open all gates."""

import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import session as session_module
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def burst_wav(path: Path, talk, seconds, seed) -> Path:
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(round(seconds * RATE)) * 0.0005
    for a, b in talk:
        lo, hi = round(a * RATE), round(b * RATE)
        x[lo:hi] = rng.standard_normal(hi - lo) * 0.2
    sf.write(path, x.astype(np.float32), RATE, subtype="PCM_16")
    return path


def talkers(session, tmp_path):
    a = burst_wav(tmp_path / "a.wav", [(0.5, 2.0), (4.0, 5.0)], 6.0, seed=1)
    b = burst_wav(tmp_path / "b.wav", [(2.5, 3.5)], 6.0, seed=2)
    session.import_media([str(a), str(b)])


def wait_job(session, job_id, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_explicit_default_options_give_the_same_gates_as_none(tmp_path):
    gates = []
    for name, args in (("Plain", {}), ("Explicit", {
            "margin_db": 12, "min_open_s": 0.4, "min_closed_s": 0.3,
            "open_before_s": 0.15, "open_after_s": 0.4, "dominance_db": 6,
            "method": "threshold"})):
        s = Session(tmp_path / f"{name}.kuulas")
        try:
            talkers(s, tmp_path)
            s.command("auto_silence", args)
            gates.append([t.gate for t in s.state.tracks])
        finally:
            s.close()
    assert gates[0] == gates[1]
    assert any(gates[0])


def test_the_options_change_what_is_closed(session, tmp_path):
    talkers(session, tmp_path)
    session.command("auto_silence", {})
    default = [t.gate for t in session.state.tracks]
    session.command("auto_silence", {"min_closed_s": 3.0})
    assert [t.gate for t in session.state.tracks] != default


def test_a_bad_option_is_refused_and_changes_nothing(session, tmp_path):
    talkers(session, tmp_path)
    steps = len(session.history.nodes())
    with pytest.raises(EditError) as e:
        session.command("auto_silence", {"margin_db": "loud"})
    assert e.value.key == "error.silence.bad_option"
    assert len(session.history.nodes()) == steps
    with pytest.raises(EditError):
        session.auto_silence_preview({"margin_db": "loud"})


def test_the_preview_is_a_job_that_changes_nothing(session, tmp_path):
    talkers(session, tmp_path)
    before = session.state
    steps = len(session.history.nodes())
    [job_id] = session.auto_silence_preview({"margin_db": 8})
    job = wait_job(session, job_id)
    assert job["state"] == "completed"
    rows = job["result"]["tracks"]
    assert len(rows) == 2
    assert all(r["close_s"] > 0 and r["now_s"] == 0 for r in rows)
    assert session.state == before
    assert len(session.history.nodes()) == steps


def test_the_preview_does_not_hold_the_session_lock(session, tmp_path, monkeypatch):
    talkers(session, tmp_path)
    started, release = threading.Event(), threading.Event()
    real = session_module.analysis.preview_silence

    def slow(*a, **k):
        started.set()
        release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(session_module.analysis, "preview_silence", slow)
    [job_id] = session.auto_silence_preview({})
    assert started.wait(10)
    assert session.lock.acquire(timeout=1)  # the analysis does not hold it
    session.lock.release()
    release.set()
    assert wait_job(session, job_id)["state"] == "completed"


def test_open_gates_clears_the_named_tracks_in_one_undo_step(session, tmp_path):
    talkers(session, tmp_path)
    session.command("auto_silence", {})
    gated = session.state
    a, b = (t.id for t in gated.tracks)
    steps = len(session.history.nodes())
    session.command("open_gates", {"track_ids": [a]})
    assert session.state.track(a).gate == ()
    assert session.state.track(b).gate == gated.track(b).gate
    assert len(session.history.nodes()) == steps + 1
    session.undo()
    assert session.state == gated


class IdleEngine:
    def __getattr__(self, name):
        raise AssertionError(name)


def test_the_preview_route_answers_a_job_and_refuses_bad_options(session, tmp_path):
    talkers(session, tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        r = c.post("/api/auto-silence/preview", json={"margin_db": 9})
        assert r.status_code == 202
        job = wait_job(session, r.json()["jobs"][0])
        assert job["state"] == "completed"
        r = c.post("/api/auto-silence/preview", json={"margin_db": "x"})
        assert r.status_code == 400


def test_open_gates_without_names_opens_every_gated_track(session, tmp_path):
    talkers(session, tmp_path)
    session.command("auto_silence", {})
    session.command("open_gates", {})
    assert not any(t.gate for t in session.state.tracks)
