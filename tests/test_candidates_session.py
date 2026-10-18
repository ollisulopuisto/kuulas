"""Cut candidates in the session and the API (WP18): material steps, undo, the lock."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import analysis
from kuulas import candidates as cm
from kuulas.clock import FLICKS
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def f(seconds: float) -> int:
    return round(seconds * FLICKS)


def fr(seconds: float) -> int:
    return round(seconds * RATE)


def words(*spec) -> list[dict]:
    return [{"w": w, "s": f(s), "e": f(e), "spk": "A"} for w, s, e in spec]


EN = words(("So", 1.0, 1.3), ("um,", 1.4, 1.7), ("I", 1.8, 1.9), ("went", 1.9, 2.2),
           ("I", 2.4, 2.5), ("went", 2.5, 2.8), ("to", 2.8, 2.9), ("the", 2.9, 3.0),
           ("shop.", 3.0, 3.5), ("And", 6.5, 6.7), ("then", 6.7, 6.9), ("er", 7.0, 7.3),
           ("we", 7.4, 7.5), ("left.", 7.5, 8.0))


def wav(path: Path, seed: int, seconds: float = 12.0) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32),
             RATE, subtype="PCM_16")
    return path


@pytest.fixture
def bare(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(wav(tmp_path / "a.wav", 1)), str(wav(tmp_path / "b.wav", 2))])
    yield s
    s.close()


#: The other mic: quiet while the first speaker pauses (3.5 to 6.5 s).
OTHER = words(("joo", 0.2, 0.5), ("okei", 9.0, 9.5))


@pytest.fixture
def session(bare):
    # The import puts files without clocks in one sync group (both start at 0),
    # so a pause is a pause only when both mics are quiet.
    a, b = bare.state.tracks
    bare.set_transcript(a.clips[0].media, EN, "transcript")
    bare.set_transcript(b.clips[0].media, OTHER, "transcript")
    return bare


def steps(s: Session) -> int:
    return len(s.history.nodes())


def store(s: Session) -> dict:
    return s.history.material.get("candidates", {})


def by_text(s: Session, text: str) -> str:
    return next(i for i, r in store(s).items() if r["text"] == text)


# -- detection ---------------------------------------------------------------------


def test_detecting_is_one_material_step_and_undo_takes_it_back(session):
    before = steps(session)
    out = session.candidates_detect()
    assert out["added"] == len(store(session)) > 0
    assert steps(session) == before + 1
    assert {r["kind"] for r in store(session).values()} == {"filler", "retake",
                                                            "silence"}
    session.undo()
    assert store(session) == {}
    session.redo()
    assert len(store(session)) == out["added"]


def test_detecting_again_commits_nothing_and_keeps_decisions(session):
    session.candidates_detect()
    um = by_text(session, "um,")
    session.candidate_set_state(um, "kept")
    before = steps(session)
    again = session.candidates_detect()
    assert again["added"] == 0
    assert steps(session) == before
    assert store(session)[um]["state"] == "kept"


def test_a_state_change_is_one_undoable_step(session):
    session.candidates_detect()
    er = by_text(session, "er")
    before = steps(session)
    session.candidate_set_state(er, "kept")
    assert steps(session) == before + 1
    assert store(session)[er]["state"] == "kept"
    session.undo()
    assert store(session)[er]["state"] == "open"


def test_ids_persist_when_the_clip_moves(session):
    session.candidates_detect()
    ids = set(store(session))
    clip = session.state.tracks[0].clips[0]
    session.edit("move_clip", {"clip_id": clip.id, "start": fr(3)})
    assert session.candidates_detect()["added"] == 0
    assert set(store(session)) == ids
    um = next(c for c in session.candidates()["candidates"] if c["text"] == "um,")
    assert (um["start"], um["end"]) == (fr(4.4), fr(4.7))


# -- applying ----------------------------------------------------------------------


def test_applying_soft_cuts_the_speakers_track_in_one_undo_step(session):
    session.candidates_detect()
    um = by_text(session, "um,")
    a, b = session.state.tracks
    before_b = session.state.tracks[1]
    n = steps(session)
    out = session.candidate_apply(um)
    assert out["tracks"] == [a.id]
    assert out["spans"] == [[fr(1.4), fr(1.7)]]
    assert steps(session) == n + 1
    track_a = session.state.track(a.id)
    assert [(c.start, c.end) for c in track_a.clips if c.muted] == [(fr(1.4), fr(1.7))]
    assert session.state.track(b.id) == before_b
    assert store(session)[um]["state"] == "cut"
    session.undo()
    assert not any(c.muted for c in session.state.track(a.id).clips)
    assert store(session)[um]["state"] == "open"


def test_a_ripple_apply_closes_the_gap_on_every_track(session):
    session.candidates_detect()
    pause = next(i for i, r in store(session).items() if r["kind"] == "silence")
    length = session.state.length
    out = session.candidate_apply(pause, mode="ripple")
    (a, b), = out["spans"]
    assert session.state.length == length - (b - a)
    assert len(out["tracks"]) == 2


def test_applying_a_cut_candidate_again_is_refused(session):
    session.candidates_detect()
    um = by_text(session, "um,")
    session.candidate_apply(um)
    with pytest.raises(cm.CandidateError):
        session.candidate_apply(um)


def test_a_cut_stretch_is_not_proposed_again_and_its_decision_stays(session):
    session.candidates_detect()
    um = by_text(session, "um,")
    session.candidate_apply(um)
    session.candidates_detect()
    assert store(session)[um]["state"] == "cut"
    assert [r["text"] for r in store(session).values()].count("um,") == 1


def test_a_preview_names_the_frames_to_skip(session):
    session.candidates_detect()
    um = by_text(session, "um,")
    n = steps(session)
    preview = session.candidate_preview(um)
    assert preview["skip"] == [[fr(1.4), fr(1.7)]]
    assert steps(session) == n  # nothing committed
    assert store(session)[um]["state"] == "open"


# -- marks -------------------------------------------------------------------------


def test_a_mark_is_a_marked_candidate_and_undoes(session):
    a = session.state.tracks[0]
    cid = session.candidate_mark(fr(9), fr(10), a.id)
    rec = store(session)[cid]
    assert (rec["kind"], rec["state"], rec["media"]) == ("marked", "open",
                                                         a.clips[0].media)
    session.undo()
    assert cid not in store(session)


def test_a_mark_survives_detection(session):
    a = session.state.tracks[0]
    cid = session.candidate_mark(fr(9), fr(10), a.id)
    session.candidates_detect()
    assert cid in store(session)


# -- the lock, old projects, unknown keys ---------------------------------------------


def test_the_lock_is_free_while_detecting(session, monkeypatch):
    seen = []
    real = cm.detect

    def spy(*args, **kwargs):
        seen.append(session.lock._is_owned())
        return real(*args, **kwargs)

    monkeypatch.setattr(cm, "detect", spy)
    session.candidates_detect()
    session.command("candidates_detect", {})
    assert seen == [False, False]


def test_level_analysis_runs_outside_the_lock_and_finds_pauses(bare, monkeypatch):
    a, b = bare.state.tracks
    seen = []

    def closed(p, store):
        seen.append(bare.lock._is_owned())
        return {a.id: ((fr(2), fr(5)),), b.id: ((fr(1), fr(6)),)}

    monkeypatch.setattr(analysis, "raw_silence_ranges", closed)
    bare.candidates_detect(levels=True)
    assert seen == [False]
    pauses = [r for r in store(bare).values() if r["kind"] == "silence"]
    keep = cm.KEEP_PAUSE_S / 2
    # Both mics closed 2 to 5 s: one pause for the whole group, on its main
    # recording's clock (both files start at the group's 0 here).
    main = bare.state.sync_groups[0].main
    assert [(r["media"], r["scope"], r["start"], r["end"]) for r in pauses] == [
        (main, "group", f(2 + keep), f(5 - keep))]


def test_a_failing_level_analysis_falls_back_to_the_transcripts(session, monkeypatch):
    def broken(p, store):
        raise OSError("disk gone")

    monkeypatch.setattr(analysis, "raw_silence_ranges", broken)
    out = session.candidates_detect(levels=True)
    assert out["added"] > 0


def test_an_old_project_without_candidates_works(bare):
    before = steps(bare)
    assert bare.candidates() == {"candidates": [], "summary": {
        "open": 0, "cut": 0, "kept": 0, "total": 0}}
    assert bare.candidates_detect()["added"] == 0
    assert steps(bare) == before  # nothing found, nothing written
    assert "candidates" not in bare.history.material
    with pytest.raises(cm.UnknownCandidateError):
        bare.candidate_set_state("knope", "kept")


def test_unknown_keys_of_a_record_survive_a_state_change(session):
    session.candidates_detect()
    um = by_text(session, "um,")
    root = session.history.material
    root["candidates"][um]["from_the_future"] = [1, 2]
    root["future_material"] = {"x": 1}
    session.history.set_material("newer kuulas", root)
    session.candidate_set_state(um, "kept")
    session.candidates_detect()
    assert store(session)[um]["from_the_future"] == [1, 2]
    assert session.history.material["future_material"] == {"x": 1}


# -- the API -----------------------------------------------------------------------


class _Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}

    def close(self):
        pass


@pytest.fixture
def client(session):
    return TestClient(create_app(session, _Engine(), language="en"))


def test_get_candidates_gives_frames_flicks_and_counts(client, session):
    assert client.post("/api/command", json={"name": "candidates_detect",
                                             "args": {}}).status_code == 200
    body = client.get("/api/candidates").json()
    um = next(c for c in body["candidates"] if c["text"] == "um,")
    assert (um["start"], um["end"]) == (fr(1.4), fr(1.7))
    assert (um["start_flicks"], um["end_flicks"]) == (f(1.4), f(1.7))
    assert um["spans"] == [[fr(1.4), fr(1.7)]]
    assert um["reason"] == "Filler “um,”"
    assert um["state"] == "open"
    assert body["summary"]["open"] == body["summary"]["total"] == len(body["candidates"])
    starts = [c["start"] for c in body["candidates"]]
    assert starts == sorted(starts)


def test_the_api_applies_keeps_and_marks(client, session):
    client.post("/api/command", json={"name": "candidates_detect", "args": {}})
    um, er = by_text(session, "um,"), by_text(session, "er")
    r = client.post("/api/command", json={"name": "candidate_apply", "args": {"id": um}})
    assert r.status_code == 200
    r = client.post("/api/command", json={"name": "candidate_set_state",
                                          "args": {"id": er, "state": "kept"}})
    assert r.status_code == 200
    track = session.state.tracks[0].id
    r = client.post("/api/command", json={"name": "candidate_mark", "args": {
        "start": fr(9), "end": fr(10), "track_id": track}})
    assert r.status_code == 200
    summary = client.get("/api/candidates").json()["summary"]
    assert (summary["cut"], summary["kept"]) == (1, 1)
    only_open = client.get("/api/candidates", params={"state": "open"}).json()
    assert all(c["state"] == "open" for c in only_open["candidates"])
    preview = client.get(f"/api/candidates/{er}/preview").json()
    assert preview["skip"] == [[fr(7.0), fr(7.3)]]


def test_api_errors_are_translated(client, session):
    r = client.post("/api/command", json={"name": "candidate_set_state",
                                          "args": {"id": "knope", "state": "kept"}})
    assert r.status_code == 404
    assert r.json()["error"]["key"] == "error.candidates.no_candidate"
    client.post("/api/command", json={"name": "candidates_detect", "args": {}})
    um = by_text(session, "um,")
    r = client.post("/api/command", json={"name": "candidate_set_state",
                                          "args": {"id": um, "state": "maybe"}},
                    headers={"Accept-Language": "fi"})
    assert r.status_code == 400
    assert r.json()["error"]["text"].startswith("”maybe” ei ole ehdokkaan tila")
    r = client.get("/api/candidates/knope/preview")
    assert r.status_code == 404
