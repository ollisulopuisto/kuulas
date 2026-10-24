"""Level blocks (Auto-mix in Kuulas, phase 2): the automixer's speech block
levelling (``speechmix.blocks``) measured in Kuulas and written as editable
clip gains, as one undo step. Synthetic noise 'speech'; no audio is played."""

import threading
import time
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import analysis, block_level, offload
from kuulas.model import Project
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000
SECONDS = 60.0
#: (start, end, rms) of the talk. The reference level is 0.05; the third block
#: is 12 dB hot (gain -12), the fourth 6 dB quiet (gain +6), the rest ordinary.
TALK = [(1, 9, 0.05), (11, 19, 0.05), (21, 29, 0.2), (31, 39, 0.025), (41, 49, 0.05)]
FLOOR = 0.0005
#: Long blocks, all ordinary: a short burst inside the first cannot move its level.
CALM = [(1, 17, 0.05), (20, 32, 0.05), (36, 46, 0.05)]


def talk_wav(path: Path, talk=TALK, burst=None) -> Path:
    rng = np.random.default_rng(3)
    x = rng.standard_normal(round(SECONDS * RATE)) * FLOOR
    for a, b, level in talk:
        lo, hi = round(a * RATE), round(b * RATE)
        x[lo:hi] = rng.standard_normal(hi - lo) * level
    if burst:  # a 1.5 s stretch 8 dB over its block, inside block 1
        lo, hi = round(burst[0] * RATE), round(burst[1] * RATE)
        x[lo:hi] *= 2.5
    sf.write(path, x.astype(np.float32), RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Blocks.kuulas")
    yield s
    s.close()


def build(session, tmp_path, **kw):
    session.import_media([str(talk_wav(tmp_path / "anna.wav", **kw))])
    [track] = session.state.tracks
    session.edit("set_track", {"track_id": track.id, "kind": "speech"})
    return session.state


def gains_of(m):
    [speaker] = m["speakers"]
    return [b["gain_db"] for b in speaker["blocks"]]


def clips_of(session):
    [track] = session.state.tracks
    return track.clips


def gain_at(session, seconds):
    frame = round(seconds * RATE)
    [clip] = [c for c in clips_of(session) if c.start <= frame < c.end]
    return clip.gain_db


# -- the measurement -------------------------------------------------------------


def test_the_blocks_and_their_gains_are_the_automixers(session, tmp_path):
    build(session, tmp_path)
    m = block_level.measure(session.state, session.store)
    assert m["reason"] is None
    assert gains_of(m) == pytest.approx([0, 0, -12, 6, 0], abs=0.6)
    [speaker] = m["speakers"]
    assert [round(b["start"] / RATE) for b in speaker["blocks"]] == [1, 11, 21, 31, 41]
    assert m["threshold_db"] == 3.0
    assert (m["max_cut_db"], m["max_boost_db"]) == (18.0, 6.0)


def test_the_measurement_reports_how_far_it_is(session, tmp_path):
    build(session, tmp_path)
    seen = []
    block_level_task = offload.call(
        "block_level", session.state, session.store,
        on_progress=lambda f, stage, detail: seen.append((f, stage, detail)))
    assert block_level_task["speakers"]
    fractions = [f for f, _s, _d in seen]
    assert fractions == sorted(fractions)
    assert 0.0 < fractions[0] < 1.0
    assert fractions[-1] == 1.0
    stages = [s for _f, s, _d in seen]
    assert stages[0] == "tracks"
    assert stages[-1] == "blocks"
    assert seen[0][2] == {"done": 1, "total": 1}


def test_no_speech_is_a_reason_not_a_crash(session, tmp_path):
    build(session, tmp_path)
    [track] = session.state.tracks
    session.edit("set_track", {"track_id": track.id, "mute": True})
    assert block_level.measure(session.state, session.store)["reason"] == "no_speech"
    with pytest.raises(EditError) as e:
        session.command("level_blocks", {})
    assert e.value.key == "error.block_level.no_speech"


def test_loud_spots_are_listed_and_not_part_of_the_gains(session, tmp_path):
    build(session, tmp_path, burst=(3, 4.6), talk=CALM)
    m = block_level.measure(session.state, session.store)
    assert gains_of(m)[0] == 0
    [loud] = m["speakers"][0]["loud"]
    assert 2.5 < loud["start"] / RATE < 3.5
    assert loud["excess_db"] > 4


def test_the_key_ignores_what_the_measurement_does_not_read(session, tmp_path):
    build(session, tmp_path)
    [track] = session.state.tracks
    before = block_level.key(session.state)
    session.edit("set_track", {"track_id": track.id, "gain_db": -4.0})
    assert block_level.key(session.state) == before
    session.edit("set_clip", {"clip_id": track.clips[0].id, "gain_db": -2.0})
    assert block_level.key(session.state) != before


def test_heard_levels_carry_clip_gain_by_either_path(session, tmp_path, monkeypatch):
    build(session, tmp_path)
    [clip] = clips_of(session)
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -6.0})
    track = session.state.tracks[0]
    raw, _ = analysis.track_levels(session.state, session.store, track)
    by_envelope, _ = analysis.track_levels(session.state, session.store, track,
                                           heard=True)
    monkeypatch.setattr(session.store, "envelope", None)  # force the audio path
    by_audio, _ = analysis.track_levels(session.state, session.store, track, heard=True)
    spoken = raw > -40
    assert np.median((by_envelope - raw)[spoken]) == pytest.approx(-6, abs=0.1)
    assert np.median((by_audio - raw)[spoken]) == pytest.approx(-6, abs=0.1)


# -- applying --------------------------------------------------------------------


def test_apply_splits_at_the_pauses_and_sets_clip_gains(session, tmp_path):
    build(session, tmp_path)
    [original] = clips_of(session)
    m = block_level.measure(session.state, session.store)
    session.command("level_blocks", {"measured": m})
    clips = clips_of(session)
    # No gap, no overlap, no media change: the pieces tile the original exactly.
    assert clips[0].start == original.start
    assert clips[-1].end == original.end
    for a, b in pairwise(clips):
        assert a.end == b.start
        assert b.offset == a.offset + a.length
        assert a.media == b.media == original.media
    assert gain_at(session, 5) == 0
    assert gain_at(session, 25) == pytest.approx(-12, abs=0.6)
    assert gain_at(session, 35) == pytest.approx(6, abs=0.6)
    # The cuts are in the pauses, not in the talk: 29..31 holds the cut between 3 and 4.
    cuts = [c.start / RATE for c in clips[1:]]
    assert all(not any(a < cut < b for a, b, _ in TALK) for cut in cuts)


def test_the_new_cuts_are_ramped_so_nothing_clicks(session, tmp_path):
    build(session, tmp_path)
    session.command("level_blocks", {})
    clips = clips_of(session)
    ramp = round(block_level.RAMP_S * RATE)
    assert len(clips) > 1
    for left, right in pairwise(clips):
        assert left.fade_out == ramp
        assert right.fade_in == ramp


def test_it_adds_to_the_gain_the_clip_already_has(session, tmp_path):
    build(session, tmp_path)
    [clip] = clips_of(session)
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -3.0})
    session.command("level_blocks", {})
    assert gain_at(session, 5) == -3.0
    assert gain_at(session, 25) == pytest.approx(-15, abs=0.6)


def test_running_it_again_gives_about_zero(session, tmp_path):
    build(session, tmp_path)
    session.command("level_blocks", {})
    again = block_level.measure(session.state, session.store)
    assert gains_of(again) == [0, 0, 0, 0, 0]
    clips, steps = clips_of(session), len(session.history.nodes())
    session.command("level_blocks", {})
    assert clips_of(session) == clips  # nothing split, nothing added
    assert len(session.history.nodes()) == steps + 1


def test_one_undo_step_restores_everything(session, tmp_path):
    build(session, tmp_path)
    before, steps = session.state, len(session.history.nodes())
    session.command("level_blocks", {"markers": True})
    assert len(session.history.nodes()) == steps + 1
    assert session.state != before
    session.undo()
    assert session.state == before
    assert block_level.block_level_current(session.state) is None


def test_unticked_blocks_are_left_alone_and_the_record_says_not_done(session, tmp_path):
    build(session, tmp_path)
    m = block_level.measure(session.state, session.store)
    hot = next(b for b in m["speakers"][0]["blocks"] if b["gain_db"] < -6)
    session.command("level_blocks", {"measured": m, "skip": [hot["id"]]})
    assert gain_at(session, 25) == 0
    assert gain_at(session, 35) == pytest.approx(6, abs=0.6)
    # A changed block was left out, so the automixer must still level it.
    assert "block_level" not in session.state.mix_done


def test_a_soft_cut_keeps_its_mute_and_gets_the_gain(session, tmp_path):
    build(session, tmp_path)
    [track] = session.state.tracks
    session.edit("mute_ranges", {"track_id": track.id,
                                 "ranges": [[round(22 * RATE), round(23 * RATE)]]})
    session.command("level_blocks", {})
    muted = [c for c in clips_of(session) if c.muted]
    assert len(muted) == 1
    assert muted[0].gain_db == pytest.approx(-12, abs=0.6)
    assert sum(c.length for c in clips_of(session)) == round(SECONDS * RATE)


def test_markers_for_loud_spots_only_when_asked(session, tmp_path):
    build(session, tmp_path, burst=(3, 4.6), talk=CALM)
    session.command("level_blocks", {})
    assert session.state.markers == ()
    session.undo()
    session.command("level_blocks", {"markers": True})
    [marker] = session.state.markers
    assert 2.5 < marker.start / RATE < 3.5
    assert "anna" in marker.name


def test_linked_tracks_and_other_speakers_are_not_touched(session, tmp_path):
    build(session, tmp_path)
    other = talk_wav(tmp_path / "ville.wav", talk=[(1, 9, 0.05), (11, 19, 0.05)])
    session.import_media([str(other)])
    ville = next(t for t in session.state.tracks if t.name.startswith("ville"))
    before = session.state.track(ville.id).clips
    session.command("level_blocks", {})
    assert session.state.track(ville.id).clips == before


# -- the record ------------------------------------------------------------------


def test_the_record_holds_until_a_clip_changes(session, tmp_path):
    build(session, tmp_path)
    session.command("level_blocks", {})
    entry = session.state.mix_done["block_level"]
    assert entry["applied"] is True
    assert entry["blocks"] == 2
    assert "set_at" in entry
    assert block_level.block_level_current(session.state) == entry
    clip = clips_of(session)[0]
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -1.0})
    assert block_level.block_level_current(session.state) is None


def test_a_new_speech_track_makes_the_record_stale(session, tmp_path):
    build(session, tmp_path)
    session.command("level_blocks", {})
    session.import_media([str(talk_wav(tmp_path / "ville.wav"))])
    session.edit("set_track", {"track_id": session.state.tracks[-1].id, "kind": "speech"})
    assert block_level.block_level_current(session.state) is None


def test_the_record_is_edit_state_and_survives_a_roundtrip(session, tmp_path):
    build(session, tmp_path)
    session.command("level_blocks", {})
    q = Project.from_json(session.state.to_json())
    assert block_level.block_level_current(q) is not None


# -- the background job and the routes --------------------------------------------


def wait_job(session, job_id, seconds=60):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_the_measure_job_changes_nothing_and_its_result_applies(session, tmp_path):
    build(session, tmp_path)
    before = session.state
    [job_id] = session.block_level_measure({})
    job = wait_job(session, job_id)
    assert job["state"] == "completed"
    assert session.state == before
    session.command("level_blocks", {"measured": job["result"]})
    assert gain_at(session, 25) == pytest.approx(-12, abs=0.6)


def test_a_stale_measurement_is_refused(session, tmp_path):
    build(session, tmp_path)
    [job_id] = session.block_level_measure({})
    m = wait_job(session, job_id)["result"]
    session.edit("set_clip", {"clip_id": clips_of(session)[0].id, "gain_db": -3.0})
    with pytest.raises(EditError) as e:
        session.command("level_blocks", {"measured": m})
    assert e.value.key == "error.block_level.stale"


def test_a_malformed_measurement_is_refused(session, tmp_path):
    build(session, tmp_path)
    for bad in ({}, {"speakers": "x"}, {"speakers": [{"blocks": 3}], "key": "k"}):
        with pytest.raises(EditError):
            session.command("level_blocks", {"measured": bad})


def test_the_job_does_not_hold_the_session_lock_and_can_be_cancelled(
        session, tmp_path, monkeypatch):
    build(session, tmp_path)
    started, release = threading.Event(), threading.Event()
    real = block_level.measure

    def slow(*a, **k):
        started.set()
        release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(block_level, "measure", slow)
    [job_id] = session.block_level_measure({})
    assert started.wait(10)
    assert session.lock.acquire(timeout=1)
    session.lock.release()
    session.jobs.cancel(job_id)
    release.set()
    assert wait_job(session, job_id)["state"] == "cancelled"


def test_measuring_streams_and_runs_in_the_worker(session, tmp_path):
    assert offload.TASKS["block_level"] == "kuulas.block_level:measure"
    assert "block_level" not in offload.SUPERSEDE


class IdleEngine:
    def __getattr__(self, name):
        raise AssertionError(name)


def test_the_routes_measure_then_apply(session, tmp_path):
    build(session, tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        r = c.post("/api/block-level/measure", json={})
        assert r.status_code == 202
        m = wait_job(session, r.json()["jobs"][0])["result"]
        r = c.post("/api/command", json={"name": "level_blocks",
                                         "args": {"measured": m, "markers": False}})
        assert r.status_code == 200
        report = r.json()["block_level"]
        assert report["blocks"] == 2
        assert report["text"]
        r = c.post("/api/command", json={"name": "level_blocks",
                                         "args": {"measured": "x"}})
        assert r.status_code == 400
