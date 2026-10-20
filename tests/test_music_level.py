"""Set music level (Auto-mix in Kuulas, phase 1): measure the speech while anyone
speaks and the beds' loudest 3 s, set the music tracks' gain to sit a chosen
distance under the speech, as one undo step."""

import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from speechmix.meter import IntegratedMeter

from kuulas import mixer, music_level
from kuulas.model import Project
from kuulas.ops import EditError
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000
SECONDS = 20.0


# -- the pure part -------------------------------------------------------------


def measured(**over):
    base = {"speech_lufs": -20.0, "bed_lufs": -15.0, "mode": "common",
            "balance": {"m1": 0.0, "m2": -6.0}, "beds": {}, "key": "k", "reason": None}
    return {**base, **over}


def test_the_change_puts_the_loudest_moment_offset_under_the_speech():
    plan = music_level.solve(measured(), -10.0)
    assert plan.change_db == -15.0  # -20 - 10 - (-15)
    assert plan.gains == {"m1": -15.0, "m2": -21.0}  # the balance is kept
    assert plan.clamped == ()


def test_the_automixer_rule_is_the_same_formula_at_minus_one():
    plan = music_level.solve(measured(), music_level.AUTOMIXER_OFFSET_DB)
    assert plan.change_db == -6.0


def test_per_track_levels_each_track_on_its_own():
    beds = {"m1": -15.0, "m2": -25.0}
    plan = music_level.solve(measured(mode="per_track", beds=beds), -10.0)
    assert plan.gains == {"m1": -15.0, "m2": -5.0}


def test_a_gain_past_the_range_is_clamped_and_said():
    plan = music_level.solve(measured(bed_lufs=-80.0, balance={"m1": 0.0}), 0.0)
    assert plan.gains == {"m1": music_level.GAIN_RANGE[1]}
    assert plan.clamped == ("m1",)


@pytest.mark.parametrize("value", ["loud", -31, 0.5, float("nan"), "-40"])
def test_a_bad_offset_is_refused(value):
    with pytest.raises(EditError) as e:
        music_level.parse_offset(value)
    assert e.value.key == "error.music_level.bad_offset"


def test_the_offset_default_and_a_comma_decimal():
    assert music_level.parse_offset(None) == -10.0
    assert music_level.parse_offset("-7,5") == -7.5


def test_no_music_and_no_speech_are_refused_with_their_reason():
    with pytest.raises(EditError) as e:
        music_level.check(measured(reason="no_music"))
    assert e.value.key == "error.music_level.no_music"
    with pytest.raises(EditError) as e:
        music_level.check(measured(reason="no_speech"))
    assert e.value.key == "error.music_level.no_speech"


def test_a_malformed_measurement_is_refused_not_crashed_on():
    for bad in (measured(speech_lufs="loud"), measured(balance=None), {}):
        with pytest.raises(EditError) as e:
            music_level.check(bad)
        assert e.value.key == "error.edit.bad_arguments"


def test_mix_done_is_edit_state_absent_when_empty():
    p = Project()
    assert "mix_done" not in p.to_dict()
    q = Project.from_dict({**p.to_dict(), "mix_done": {"bed_level": {"offset_db": -10}}})
    assert q.mix_done == {"bed_level": {"offset_db": -10}}
    assert Project.from_json(q.to_json()) == q


# -- a synthetic project -------------------------------------------------------


def talk_wav(path: Path, talk, level, seed) -> Path:
    """Noise 'speech' at ``level`` in the ``talk`` stretches, a quiet floor elsewhere."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(round(SECONDS * RATE)) * 0.0005
    for a, b in talk:
        lo, hi = round(a * RATE), round(b * RATE)
        x[lo:hi] = rng.standard_normal(hi - lo) * level
    sf.write(path, x.astype(np.float32), RATE, subtype="PCM_16")
    return path


def music_wav(path: Path) -> Path:
    """A stereo sine bed, louder in its middle 5 s (the loudest moment)."""
    n = round(SECONDS * RATE)
    tt = np.arange(n) / RATE
    amp = np.full(n, 0.05)
    amp[round(8 * RATE):round(13 * RATE)] = 0.2
    x = (np.sin(2 * np.pi * 440 * tt) * amp).astype(np.float32)
    sf.write(path, np.stack([x, x], axis=1), RATE, subtype="FLOAT")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Bed.kuulas")
    yield s
    s.close()


def build(session, tmp_path, music=True, speech=True):
    paths = []
    if speech:
        paths += [str(talk_wav(tmp_path / "anna.wav", [(1, 6), (12, 17)], 0.2, 1)),
                  str(talk_wav(tmp_path / "ville.wav", [(6.5, 11.5)], 0.1, 2))]
    if music:
        paths.append(str(music_wav(tmp_path / "bed.wav")))
    session.import_media(paths)
    p = session.state
    for track in p.tracks:
        bed = p.media_item(track.clips[0].media).name.startswith("bed")
        kind = "music" if bed else "speech"
        session.edit("set_track", {"track_id": track.id, "kind": kind})
    return session.state


def music_ids(session):
    return [t.id for t in session.state.tracks if t.kind == "music"]


def heard_peak(session) -> float:
    """The beds' loudest 3 s, measured as heard (with the track gain)."""
    p = session.state
    meter = IntegratedMeter(RATE)
    for t in p.tracks:
        if t.kind == "music":
            meter.add(mixer.track_stem(t, session.store, 0, p.length, 2,
                                       as_heard=True, rate=RATE))
    return meter.short_term_max()


def test_the_measurement_and_the_applied_gain(session, tmp_path):
    build(session, tmp_path)
    m = music_level.measure(session.state, session.store)
    assert m["reason"] is None
    # Noise at 0.2 and 0.1 rms: both inside the relative gate.
    assert -20 < m["speech_lufs"] < -10
    # The sine at 0.2 peak in the middle, stereo. Analytic: 0.2 peak = -17 dBFS
    # rms a side, +3 for two sides, -0.691 (BS.1770), ~0 K-weighting at 440 Hz.
    assert m["bed_lufs"] == pytest.approx(-14.7, abs=0.2)
    session.command("set_music_level", {"offset_db": -10})
    [mid] = music_ids(session)
    gain = session.state.track(mid).gain_db
    assert gain == pytest.approx(m["speech_lufs"] - 10 - m["bed_lufs"], abs=0.01)
    assert heard_peak(session) == pytest.approx(m["speech_lufs"] - 10, abs=0.05)
    print(f"speech {m['speech_lufs']} LUFS, bed {m['bed_lufs']} LUFS, gain {gain} dB")


def test_running_it_twice_gives_the_same_gains(session, tmp_path):
    build(session, tmp_path)
    [mid] = music_ids(session)
    session.edit("set_track", {"track_id": mid, "gain_db": 5.0})  # the gain is excluded
    session.command("set_music_level", {"offset_db": -12})
    first = session.state.track(mid).gain_db
    session.command("set_music_level", {"offset_db": -12})
    assert session.state.track(mid).gain_db == first


def test_clip_gain_counts_as_heard(session, tmp_path):
    build(session, tmp_path)
    [mid] = music_ids(session)
    session.command("set_music_level", {})
    plain = session.state.track(mid).gain_db
    clip = session.state.track(mid).clips[0]
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -6.0})
    session.command("set_music_level", {})
    assert session.state.track(mid).gain_db == pytest.approx(plain + 6.0, abs=0.05)


def test_a_muted_speech_track_does_not_count(session, tmp_path):
    build(session, tmp_path)
    both = music_level.measure(session.state, session.store)["speech_lufs"]
    quiet = next(t for t in session.state.tracks if t.name.startswith("ville"))
    session.edit("set_track", {"track_id": quiet.id, "mute": True})
    alone = music_level.measure(session.state, session.store)["speech_lufs"]
    assert alone > both  # only the loud talker is left


def test_common_mode_keeps_the_balance_of_two_beds(session, tmp_path):
    build(session, tmp_path)
    second = music_wav(tmp_path / "bed2.wav")
    session.import_media([str(second)])
    new = session.state.tracks[-1]
    session.edit("set_track", {"track_id": new.id, "kind": "music", "gain_db": -6.0})
    a, b = music_ids(session)
    session.command("set_music_level", {})
    assert (session.state.track(a).gain_db - session.state.track(b).gain_db
            == pytest.approx(6.0, abs=0.01))


def test_one_undo_step_restores_the_gains_and_the_record(session, tmp_path):
    build(session, tmp_path)
    before = session.state
    steps = len(session.history.nodes())
    session.command("set_music_level", {"offset_db": -10})
    assert len(session.history.nodes()) == steps + 1
    entry = session.state.mix_done["bed_level"]
    assert entry["offset_db"] == -10.0
    assert music_level.bed_level_current(session.state) == entry
    session.undo()
    assert session.state == before
    assert music_level.bed_level_current(session.state) is None


def test_the_record_stops_holding_when_the_music_gain_moves(session, tmp_path):
    build(session, tmp_path)
    session.command("set_music_level", {})
    [mid] = music_ids(session)
    session.edit("set_track", {"track_id": mid, "gain_db": 0.0})
    assert music_level.bed_level_current(session.state) is None


def test_the_history_entry_carries_the_numbers(session, tmp_path):
    build(session, tmp_path)
    session.command("set_music_level", {"offset_db": -10})
    report = session.last_music_level
    assert report["offset_db"] == -10.0
    assert report["was_db"] is not None
    label = session.history.nodes()[-1]["label"]
    assert "10" in label


def test_no_music_is_a_clear_error_and_changes_nothing(session, tmp_path):
    build(session, tmp_path, music=False)
    steps = len(session.history.nodes())
    with pytest.raises(EditError) as e:
        session.command("set_music_level", {})
    assert e.value.key == "error.music_level.no_music"
    assert len(session.history.nodes()) == steps


def test_no_speech_is_a_clear_error(session, tmp_path):
    build(session, tmp_path, speech=False)
    with pytest.raises(EditError) as e:
        session.command("set_music_level", {})
    assert e.value.key == "error.music_level.no_speech"


# -- the background job ----------------------------------------------------------


def wait_job(session, job_id, seconds=30):
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
    [job_id] = session.music_level_measure({})
    job = wait_job(session, job_id)
    assert job["state"] == "completed"
    m = job["result"]
    assert m["reason"] is None
    assert m["speech_lufs"] is not None
    assert session.state == before
    session.command("set_music_level", {"offset_db": -10, "measured": m})
    [mid] = music_ids(session)
    assert session.state.track(mid).gain_db == pytest.approx(
        m["speech_lufs"] - 10 - m["bed_lufs"], abs=0.01)


def test_a_stale_measurement_is_refused(session, tmp_path):
    build(session, tmp_path)
    [job_id] = session.music_level_measure({})
    m = wait_job(session, job_id)["result"]
    [mid] = music_ids(session)
    clip = session.state.track(mid).clips[0]
    session.edit("set_clip", {"clip_id": clip.id, "gain_db": -3.0})
    with pytest.raises(EditError) as e:
        session.command("set_music_level", {"measured": m})
    assert e.value.key == "error.music_level.stale"


def test_the_job_reports_no_music_without_failing(session, tmp_path):
    build(session, tmp_path, music=False)
    [job_id] = session.music_level_measure({})
    job = wait_job(session, job_id)
    assert job["state"] == "completed"
    assert job["result"]["reason"] == "no_music"


def test_the_job_does_not_hold_the_session_lock_and_can_be_cancelled(
        session, tmp_path, monkeypatch):
    build(session, tmp_path)
    started, release = threading.Event(), threading.Event()
    real = music_level.measure

    def slow(*a, **k):
        started.set()
        release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(music_level, "measure", slow)
    [job_id] = session.music_level_measure({})
    assert started.wait(10)
    assert session.lock.acquire(timeout=1)
    session.lock.release()
    session.jobs.cancel(job_id)
    release.set()
    assert wait_job(session, job_id)["state"] == "cancelled"


# -- the routes --------------------------------------------------------------------


class IdleEngine:
    def __getattr__(self, name):
        raise AssertionError(name)


def test_the_routes_measure_then_apply_with_the_numbers(session, tmp_path):
    build(session, tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(session, IdleEngine(), language="en", ui_dir=ui)) as c:
        r = c.post("/api/music-level/measure", json={})
        assert r.status_code == 202
        m = wait_job(session, r.json()["jobs"][0])["result"]
        r = c.post("/api/command", json={"name": "set_music_level",
                                         "args": {"offset_db": -10, "measured": m}})
        assert r.status_code == 200
        report = r.json()["music_level"]
        assert report["offset_db"] == -10.0
        assert report["text"].startswith("Music set to 10.0 dB under the speech")
        r = c.post("/api/command", json={"name": "set_music_level",
                                         "args": {"offset_db": "x"}})
        assert r.status_code == 400
