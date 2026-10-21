"""Track kinds and music ducking (WP22).

- Track.kind: speech, music (speech-mix was removed 2026-10-19)
- Track.speaker: defaults to "" (track's name), grouping tracks into lanes
- duck_music: ducking music beds under speech using nhsx.musicbed.curve
"""

from threading import Event
from time import monotonic, sleep

import numpy as np
import pytest
import soundfile as sf
from nhsx import musicbed

from kuulas import analysis, automix, music_duck, offload, ops
from kuulas.model import Media, Project, Track
from kuulas.ops import EditError
from kuulas.session import Session


def wait_job(session, job_id):
    end = monotonic() + 5
    while monotonic() < end:
        job = next(item for item in session.jobs.list() if item["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            return job
        sleep(0.01)
    raise AssertionError("duck measurement job did not finish")


RATE = 8000
SEC = 16


class MemoryStore:
    def __init__(self, arrays, rate=RATE):
        self.arrays = arrays
        self.rate = rate

    def read(self, media_id, first, count):
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


def speech(rng, seconds):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(n)).astype(np.float32)


def test_track_kind_validation_and_speaker_field():
    p = Project(rate=RATE)
    p = ops.add_track(p, track_id="t1", name="Track 1", kind="speech")
    assert p.track("t1").kind == "speech"
    assert p.track("t1").speaker == ""

    p = ops.set_track(p, "t1", kind="music")
    assert p.track("t1").kind == "music"

    p = ops.set_track(p, "t1", speaker="Host")
    assert p.track("t1").speaker == "Host"

    with pytest.raises(EditError) as err:
        ops.set_track(p, "t1", kind="invalid-kind")
    assert err.value.key == "error.edit.bad_track_kind"

    # speech-mix was removed (2026-10-19): editing to it is an error now
    with pytest.raises(EditError) as err:
        ops.set_track(p, "t1", kind="speech-mix")
    assert err.value.key == "error.edit.bad_track_kind"
    with pytest.raises(EditError):
        ops.add_track(p, track_id="t2", kind="speech-mix")


def test_saved_speech_mix_kind_loads_as_speech():
    # Projects and history snapshots saved before 2026-10-19 hold "speech-mix".
    data = {"id": "t1", "name": "Zoom", "kind": "speech-mix", "clips": []}
    assert Track.from_dict(data).kind == "speech"
    p = Project.from_dict({"rate": RATE, "tracks": [data], "media": [], "buses": []})
    assert p.track("t1").kind == "speech"
    assert "speech-mix" not in str(p.to_dict())


def test_old_project_state_without_speaker_loads():
    # Backward compatibility: old Track dict without "speaker" key
    data = {
        "id": "t1",
        "name": "Old Track",
        "kind": "speech",
        "gain_db": 0.0,
        "pan": 0.0,
        "mute": False,
        "solo": False,
        "clips": [],
        "automation": [],
    }
    t = Track.from_dict(data)
    assert t.id == "t1"
    assert t.speaker == ""
    assert t.kind == "speech"

    # And full Project round-trip
    p_data = {
        "rate": RATE,
        "tracks": [data],
        "media": [],
        "buses": [],
    }
    p = Project.from_dict(p_data)
    assert p.track("t1").speaker == ""


def test_track_duck_is_optional_and_unknown_to_old_readers():
    track = Track(id="m", name="Music", kind="music")
    assert "duck" not in track.to_dict()
    assert Track.from_dict({**track.to_dict(), "duck": False}).duck is False
    assert Track.from_dict({**track.to_dict(), "duck": False}).extra == {}

    old = Track.from_dict({**track.to_dict(), "future_duck": False})
    assert old.extra["future_duck"] is False
    assert old.to_dict()["future_duck"] is False


def test_set_track_accepts_duck():
    p = ops.add_track(Project(rate=RATE), track_id="m", name="Music", kind="music")
    p = ops.set_track(p, "m", duck=False)
    assert p.track("m").duck is False
    with pytest.raises(EditError) as err:
        ops.set_track(p, "m", duck="false")
    assert err.value.key == "error.edit.bad_arguments"


def test_tracks_with_the_same_speaker_are_one_lane():
    rng = np.random.default_rng(10)
    n = 10 * RATE
    mic1 = np.zeros(n, dtype=np.float32)
    mic2 = np.zeros(n, dtype=np.float32)
    # Speaker talks in two segments on two different tracks
    mic1[:3 * RATE] = speech(rng, 3)
    mic2[5 * RATE:8 * RATE] = speech(rng, 3)
    store = MemoryStore({"m1": mic1[None, :], "m2": mic2[None, :]})

    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m1", name="m1.wav", channels=1, frames=n))
    p = ops.add_media(p, Media(id="m2", name="m2.wav", channels=1, frames=n))
    p = ops.add_track(p, track_id="t1", name="Mic 1", speaker="Anna")
    p = ops.add_track(p, track_id="t2", name="Mic 2", speaker="Anna")
    p = ops.add_clip(p, track_id="t1", media_id="m1", clip_id="c1")
    p = ops.add_clip(p, track_id="t2", media_id="m2", clip_id="c2")

    lanes = analysis.speech_lanes(p, store)
    # Both tracks share speaker "Anna", so they should form a single lane
    assert len(lanes.speakers) == 1
    assert lanes.speakers[0].name == "Anna"
    lane = lanes.speakers[0]
    # The combined lane is talking during both segments
    hop = analysis.hop_frames(RATE)
    assert lane.on[int(1.5 * RATE / hop)]
    assert lane.on[int(6.5 * RATE / hop)]


def test_music_automation_follows_nhsx_musicbed_curve():
    rng = np.random.default_rng(40)
    n = 25 * RATE
    anna = np.zeros(n, dtype=np.float32)
    # Speech at 6-10s
    anna[6 * RATE:10 * RATE] = speech(rng, 4)
    music_audio = 0.2 * rng.standard_normal((2, n)).astype(np.float32)
    store = MemoryStore({
        "a": anna[None, :],
        "m": music_audio,
    })

    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="a", name="a.wav", channels=1, frames=n))
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=2, frames=n))
    p = ops.add_track(p, track_id="A", name="Anna", kind="speech")
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    p = ops.add_clip(p, track_id="A", media_id="a", clip_id="ca")
    # Music clip from 2s to 20s
    p = ops.add_clip(p, track_id="M", media_id="m", start=2 * RATE, offset=0,
                     length=18 * RATE, clip_id="cm")

    p_ducked = analysis.duck_music(p, store)
    auto = p_ducked.track("M").automation
    assert auto

    # Directly compute expected curve from nhsx.musicbed.curve
    intervals = analysis.anyone_talking_intervals(p, store)
    expected_curve = musicbed.curve(
        start=2.0,
        end=20.0,
        speech=intervals,
        # The music starts before the first speech, so analysis.duck_music asks for the
        # cold-open rise (newer nhsx shapes the rise differently for it).
        cold_open=True,
    )
    assert expected_curve is not None
    expected_points = [(round((2.0 + s) * RATE), db) for s, db in expected_curve]
    assert auto == tuple(expected_points)


def test_music_track_with_duck_disabled_keeps_its_automation():
    track = Track(id="m", name="Music", kind="music", duck=False,
                  automation=((12, -9.0),))
    p = Project(rate=RATE, tracks=(track,))

    result = analysis.duck_music(p, MemoryStore({}), intervals=[])

    assert result.track("m").automation == ((12, -9.0),)


def test_sidechain_measure_builds_automation_only_for_enabled_music_tracks():
    rng = np.random.default_rng(62)
    n = 8 * RATE
    voice = np.zeros(n, dtype=np.float32)
    voice[2 * RATE:6 * RATE] = speech(rng, 4)
    store = MemoryStore({"voice": voice[None, :]})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="voice", name="voice.wav", channels=1, frames=n))
    p = ops.add_track(p, track_id="S", name="Host", kind="speech")
    p = ops.add_clip(p, track_id="S", media_id="voice", clip_id="cs")
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    p = ops.add_clip(p, track_id="M", media_id="voice", clip_id="cm")
    p = ops.add_track(p, track_id="X", name="FX", kind="music")
    p = ops.set_track(p, "X", duck=False)
    p = ops.add_clip(p, track_id="X", media_id="voice", clip_id="cx")

    measured = analysis.duck_sidechain_measure(p, store)

    points = measured["curves"]["M"]
    assert measured["speech_lufs"] is not None
    assert points
    assert min(value for _, value in points) < -3
    assert "X" not in measured["curves"]


def test_sidechain_measure_gain_matches_speech_to_the_reference_level():
    def deepest(scale):
        rng = np.random.default_rng(63)
        n = 8 * RATE
        voice = np.zeros(n, dtype=np.float32)
        voice[2 * RATE:6 * RATE] = speech(rng, 4) * scale
        store = MemoryStore({"voice": voice[None, :]})
        p = Project(rate=RATE)
        p = ops.add_media(p, Media(id="voice", name="voice.wav", channels=1, frames=n))
        p = ops.add_track(p, track_id="S", name="Host", kind="speech")
        p = ops.add_clip(p, track_id="S", media_id="voice", clip_id="cs")
        p = ops.add_track(p, track_id="M", name="Music", kind="music")
        p = ops.add_clip(p, track_id="M", media_id="voice", clip_id="cm")
        measured = analysis.duck_sidechain_measure(p, store)
        return min(value for _, value in measured["curves"]["M"])

    assert deepest(1.0) == pytest.approx(deepest(0.25), abs=0.5)


def test_sidechain_measure_skips_curves_when_there_is_no_speech():
    n = 2 * RATE
    store = MemoryStore({"voice": np.zeros((1, n), dtype=np.float32)})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="voice", name="voice.wav", channels=1, frames=n))
    p = ops.add_track(p, track_id="S", name="Host", kind="speech")
    p = ops.add_clip(p, track_id="S", media_id="voice", clip_id="cs")
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    p = ops.add_clip(p, track_id="M", media_id="voice", clip_id="cm")

    measured = analysis.duck_sidechain_measure(p, store)

    assert measured["speech_lufs"] is None
    assert measured["curves"] == {}


def test_sidechain_command_writes_one_undoable_track_curve_and_done_record(tmp_path):
    session = Session(tmp_path / "Sidechain.kuulas", rate=RATE)
    try:
        p = ops.add_track(session.state, track_id="M", name="Music", kind="music")
        p = ops.set_track(p, "M", duck=True)
        session._commit("setup", p, "setup", {})
        measured = {
            "key": analysis.duck_key(p), "style": "sidechain",
            "curves": {"M": [(0, 0.0), (RATE, -8.0), (2 * RATE, 0.0)]},
        }
        before = session.history.head

        result = session.command("duck_music", {
            "style": "sidechain", "measured": measured,
        })

        assert result.track("M").automation == tuple(measured["curves"]["M"])
        assert result.mix_done["music_duck"]["tracks"]["M"] == music_duck.signature(
            result.track("M"))
        assert session.history.head != before
        assert session.undo()
        assert not session.state.track("M").automation
        assert "music_duck" not in session.state.mix_done
    finally:
        session.close()


def test_sidechain_stale_measurement_is_refused(tmp_path):
    session = Session(tmp_path / "SidechainStale.kuulas", rate=RATE)
    try:
        p = ops.add_track(session.state, track_id="M", name="Music", kind="music")
        session._commit("setup", p, "setup", {})
        measured = {"key": analysis.duck_key(p), "style": "sidechain", "curves": {}}
        session.edit("set_track", {"track_id": "M", "gain_db": -3})

        with pytest.raises(EditError) as err:
            session.command("duck_music", {"style": "sidechain", "measured": measured})

        assert err.value.key == "error.music_duck.stale"
    finally:
        session.close()


def test_sidechain_with_no_written_curve_leaves_automixer_ducking_available(tmp_path):
    session = Session(tmp_path / "SidechainSilent.kuulas", rate=RATE)
    try:
        p = ops.add_track(session.state, track_id="M", name="Music", kind="music")
        p = ops.set_track_automation(p, "M", [(0, -6.0)])
        session._commit("setup", p, "setup", {})
        measured = {"key": analysis.duck_key(p), "style": "sidechain", "curves": {}}

        result = session.command("duck_music", {
            "style": "sidechain", "measured": measured,
        })

        assert result.track("M").automation == ()
        assert "music_duck" not in result.mix_done
    finally:
        session.close()


def test_music_duck_measurement_is_a_background_job_outside_the_session_lock(
        tmp_path, monkeypatch):
    session = Session(tmp_path / "DuckJob.kuulas", rate=RATE)
    started, release = Event(), Event()

    def slow_measure(*_args, **_kwargs):
        started.set()
        release.wait(2)
        return []

    monkeypatch.setattr(offload, "call", slow_measure)
    try:
        [job_id] = session.duck_music_measure({})
        assert started.wait(2)
        assert session.lock.acquire(timeout=1)
        session.lock.release()
        release.set()
        job = wait_job(session, job_id)
        assert job["state"] == "completed"
        assert job["result"]["key"] == analysis.duck_key(session.state)
    finally:
        release.set()
        session.close()


def test_sidechain_measurement_uses_the_offload_worker_and_remains_lock_free(
        tmp_path, monkeypatch):
    session = Session(tmp_path / "DuckSidechainJob.kuulas", rate=RATE)
    calls = []

    def measure(task, snapshot, store, **kwargs):
        calls.append((task, kwargs))
        return {"key": analysis.duck_key(snapshot), "speech_lufs": -19.0, "curves": {}}

    monkeypatch.setattr(offload, "call", measure)
    try:
        [job_id] = session.duck_music_measure({"style": "sidechain", "ratio": 4})
        job = wait_job(session, job_id)

        assert job["state"] == "completed"
        assert job["result"]["style"] == "sidechain"
        assert calls[0][0] == "duck_sidechain"
        assert calls[0][1]["ratio"] == 4.0
    finally:
        session.close()


def test_sidechain_measurement_rejects_invalid_options(tmp_path):
    session = Session(tmp_path / "DuckSidechainBadOptions.kuulas", rate=RATE)
    try:
        with pytest.raises(EditError):
            session.duck_music_measure({"style": "sidechain", "ratio": 0})
        with pytest.raises(EditError):
            session.duck_music_measure({"style": "other"})
    finally:
        session.close()


def test_cold_open_bed_sits_under_the_first_words():
    rng = np.random.default_rng(50)
    n = 20 * RATE
    speech_audio = np.zeros(n, dtype=np.float32)
    # Speech begins at 5s
    speech_audio[5 * RATE:12 * RATE] = speech(rng, 7)
    music_audio = 0.2 * rng.standard_normal((2, n)).astype(np.float32)
    store = MemoryStore({
        "s": speech_audio[None, :],
        "m": music_audio,
    })

    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="s", name="s.wav", channels=1, frames=n))
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=2, frames=n))
    p = ops.add_track(p, track_id="S", name="Host", kind="speech")
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    p = ops.add_clip(p, track_id="S", media_id="s", clip_id="cs")
    # Music starts at 0s, before first speech at 5s -> cold_open=True
    p = ops.add_clip(p, track_id="M", media_id="m", start=0, offset=0,
                     length=15 * RATE, clip_id="cm")

    p_ducked = analysis.duck_music(p, store)
    auto = p_ducked.track("M").automation
    assert auto

    # Level before the plateau / under opening words should reflect cold_open
    intervals = analysis.anyone_talking_intervals(p, store)
    expected_curve = musicbed.curve(0.0, 15.0, intervals, cold_open=True)
    expected_points = [(round(s * RATE), db) for s, db in expected_curve]
    assert auto == tuple(expected_points)


def test_session_duck_music_command(tmp_path):
    rng = np.random.default_rng(60)
    rate = 48000
    speech_path = tmp_path / "speech.wav"
    music_path = tmp_path / "music.wav"
    n = 10 * rate
    x_speech = np.zeros(n, dtype=np.float32)
    x_speech[2 * rate:6 * rate] = (rng.standard_normal(4 * rate) * 0.2).astype(np.float32)
    sf.write(speech_path, x_speech, rate, subtype="PCM_16")
    x_music = (rng.standard_normal((n, 2)) * 0.1).astype(np.float32)
    sf.write(music_path, x_music, rate, subtype="PCM_16")

    s = Session(tmp_path / "DuckTest.kuulas", rate=rate)
    s.import_media([str(speech_path), str(music_path)])
    music_track_id = s.state.tracks[1].id
    s.edit("set_track", {"track_id": music_track_id, "kind": "music"})

    result = s.duck_music()
    assert result.track(music_track_id).automation
    record = result.mix_done["music_duck"]
    assert record["applied"] is True
    assert record["tracks"] == {
        music_track_id: music_duck.signature(result.track(music_track_id))}
    assert automix.done_in_kuulas(result)["music_duck"]["current"] is True
    head_node = next(n for n in s.history.nodes() if n["id"] == s.history.head)
    assert head_node["label"] == "Duck music"


    # Undo restores state
    assert s.undo()
    assert not s.state.track(music_track_id).automation
    assert "music_duck" not in s.state.mix_done



