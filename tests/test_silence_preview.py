"""The Auto-Silence live preview through the session and the API: measure once
(a job), decide per options in-process without the session lock, listen
through the engine's overlay, accept as one undo step."""

import threading

import pytest
from fastapi.testclient import TestClient
from test_silence_session import talkers, wait_job

from kuulas import analysis
from kuulas import session as session_module
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session
from kuulas.silence_options import SilenceOptions


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def measured(session):
    out = session.silence_measure()
    if out["ready"]:
        return out
    job = wait_job(session, out["jobs"][0])
    assert job["state"] == "completed", job
    return session.silence_measure()


def test_measuring_is_a_job_once_and_then_ready_at_once(session, tmp_path):
    talkers(session, tmp_path)
    first = session.silence_measure()
    assert first["ready"] is False
    assert len(first["jobs"]) == 1
    # Asked again while it runs: the same job, not a second one.
    again = session.silence_measure()
    assert again["ready"] or again["jobs"] == first["jobs"]
    wait_job(session, first["jobs"][0])
    done = session.silence_measure()
    assert done == {"ready": True, "jobs": [], "key": analysis.silence_key(session.state)}


def test_the_measure_job_reports_progress_per_track(session, tmp_path):
    talkers(session, tmp_path)
    job = wait_job(session, session.silence_measure()["jobs"][0])
    assert job["kind"] == "silence_measure"
    assert job["result"]["tracks"] == 2


def test_ranges_before_a_measure_are_refused(session, tmp_path):
    talkers(session, tmp_path)
    with pytest.raises(session_module.SilenceNotMeasuredError):
        session.silence_preview_ranges({})


def test_ranges_are_what_auto_silence_would_close(session, tmp_path):
    talkers(session, tmp_path)
    measured(session)
    for args in ({}, {"margin_db": 6}, {"min_closed_s": 2.0, "open_after_s": 1.0}):
        out = session.silence_preview_ranges(args)
        opts = SilenceOptions(**{k: float(v) for k, v in args.items()})
        want = analysis.silence_ranges(session.state, session.store, opts)
        got = {r["track_id"]: [tuple(x) for x in r["ranges"]] for r in out["tracks"]}
        assert got == {k: list(v) for k, v in want.items()}
        assert out["key"] == analysis.silence_key(session.state)
        assert all(r["total_s"] == pytest.approx(6.0) for r in out["tracks"])


def test_bad_options_are_refused(session, tmp_path):
    talkers(session, tmp_path)
    measured(session)
    with pytest.raises(EditError):
        session.silence_preview_ranges({"margin_db": "loud"})


def test_an_edit_that_leaves_the_speech_audio_keeps_the_measure(session, tmp_path):
    talkers(session, tmp_path)
    measured(session)
    a = session.state.tracks[0].id
    session.edit("set_track", {"track_id": a, "gain_db": -4.0})
    session.command("auto_silence", {})  # gates: not in the key
    assert session.silence_measure()["ready"] is True
    session.silence_preview_ranges({})


def test_an_edit_to_the_speech_audio_drops_the_measure(session, tmp_path):
    talkers(session, tmp_path)
    measured(session)
    clip = session.state.tracks[0].clips[0].id
    session.edit("trim_clip", {"clip_id": clip, "start": 48000})
    with pytest.raises(session_module.SilenceNotMeasuredError):
        session.silence_preview_ranges({})
    again = session.silence_measure()
    assert again["ready"] is False
    assert len(again["jobs"]) == 1
    wait_job(session, again["jobs"][0])
    session.silence_preview_ranges({})


def test_ranges_are_decided_without_the_session_lock(session, tmp_path, monkeypatch):
    talkers(session, tmp_path)
    measured(session)
    started, release = threading.Event(), threading.Event()
    real = analysis.silence_ranges_from

    def slow(*a, **k):
        started.set()
        release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(session_module.analysis, "silence_ranges_from", slow)
    worker = threading.Thread(target=lambda: session.silence_preview_ranges({}))
    worker.start()
    assert started.wait(10)
    assert session.lock.acquire(timeout=1)
    session.lock.release()
    release.set()
    worker.join(10)


def test_accept_commits_the_previewed_ranges_as_one_undo_step(session, tmp_path):
    talkers(session, tmp_path)
    measured(session)
    before = session.state
    steps = len(session.history.nodes())
    preview = session.silence_preview_ranges({"margin_db": 8})
    session.silence_accept({"margin_db": 8, "key": preview["key"]})
    assert len(session.history.nodes()) == steps + 1
    for row in preview["tracks"]:
        gate = session.state.track(row["track_id"]).gate
        assert [list(r) for r in gate] == row["ranges"]
    session.undo()
    assert session.state == before


def test_accept_refuses_a_stale_preview(session, tmp_path):
    talkers(session, tmp_path)
    measured(session)
    key = session.silence_preview_ranges({})["key"]
    clip = session.state.tracks[1].clips[0].id
    session.edit("trim_clip", {"clip_id": clip, "start": 4800})
    steps = len(session.history.nodes())
    with pytest.raises(EditError) as e:
        session.silence_accept({"key": key})
    assert e.value.key == "error.silence.stale"
    assert len(session.history.nodes()) == steps


# -- the routes ----------------------------------------------------------------------


class OverlayEngine:
    """What the routes need of the engine: the overlay, and nothing else."""

    def __init__(self):
        self.overlays = []

    def set_silence_overlay(self, ranges):
        self.overlays.append(ranges)


@pytest.fixture
def client(session, tmp_path):
    ui = tmp_path / "ui"
    ui.mkdir()
    engine = OverlayEngine()
    with TestClient(create_app(session, engine, language="en", ui_dir=ui)) as c:
        c.engine = engine
        yield c


def test_the_routes_measure_preview_listen_and_accept(session, tmp_path, client):
    talkers(session, tmp_path)
    r = client.post("/api/silence/ranges", json={"seq": 1})
    assert r.status_code == 409
    assert r.json()["error"]["key"] == "error.silence.not_measured"
    r = client.post("/api/silence/measure", json={})
    assert r.status_code == 200
    body = r.json()
    if not body["ready"]:
        wait_job(session, body["jobs"][0])
    assert client.post("/api/silence/measure", json={}).json()["ready"] is True
    r = client.post("/api/silence/ranges", json={"margin_db": 9, "seq": 2})
    assert r.status_code == 200
    rows = r.json()["tracks"]
    assert len(rows) == 2
    # The engine plays the preview: the ranges as an overlay, by track.
    assert client.engine.overlays[-1] == {row["track_id"]: row["ranges"] for row in rows}
    r = client.post("/api/silence/accept", json={"margin_db": 9, "key": r.json()["key"]})
    assert r.status_code == 200
    assert client.engine.overlays[-1] is None
    assert all(t.gate for t in session.state.tracks)


def test_an_older_answer_does_not_replace_a_newer_overlay(session, tmp_path, client):
    talkers(session, tmp_path)
    body = client.post("/api/silence/measure", json={}).json()
    if not body["ready"]:
        wait_job(session, body["jobs"][0])
    client.post("/api/silence/ranges", json={"margin_db": 6, "seq": 5})
    newest = client.engine.overlays[-1]
    client.post("/api/silence/ranges", json={"margin_db": 18, "seq": 4})
    assert client.engine.overlays[-1] == newest


def test_close_clears_the_overlay_and_commits_nothing(session, tmp_path, client):
    talkers(session, tmp_path)
    before = session.state
    r = client.post("/api/silence/close", json={})
    assert r.status_code == 200
    assert client.engine.overlays[-1] is None
    assert session.state == before


def test_a_stale_measure_clears_the_overlay(session, tmp_path, client):
    talkers(session, tmp_path)
    body = client.post("/api/silence/measure", json={}).json()
    if not body["ready"]:
        wait_job(session, body["jobs"][0])
    client.post("/api/silence/ranges", json={"seq": 1})
    clip = session.state.tracks[0].clips[0].id
    session.edit("trim_clip", {"clip_id": clip, "start": 4800})
    r = client.post("/api/silence/ranges", json={"seq": 2})
    assert r.status_code == 409
    assert client.engine.overlays[-1] is None


def test_a_cancelled_measure_keeps_nothing(session, tmp_path, monkeypatch):
    talkers(session, tmp_path)
    started, release = threading.Event(), threading.Event()
    real = analysis.measure_silence_track

    def slow(*a, **k):
        started.set()
        release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(analysis, "measure_silence_track", slow)
    [job_id] = session.silence_measure()["jobs"]
    assert started.wait(10)
    session.jobs.cancel(job_id)
    release.set()
    assert wait_job(session, job_id)["state"] == "cancelled"
    with pytest.raises(session_module.SilenceNotMeasuredError):
        session.silence_preview_ranges({})


def test_the_worker_task_is_the_per_track_measure():
    from kuulas import offload  # noqa: PLC0415 - only this test needs it

    assert offload.resolve("silence_track_levels") is analysis.measure_silence_track
