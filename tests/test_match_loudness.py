from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import ops
from kuulas import session as sm
from kuulas.loudness import measure_clip
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000


def make_tone_wav(path: Path, target_lufs: float, seconds: float = 3.0) -> Path:
    t = np.linspace(0, seconds, round(seconds * RATE), endpoint=False)
    sine = np.sin(2 * np.pi * 1000 * t)
    amp = 10 ** ((target_lufs + 3.01) / 20)
    audio = (amp * sine).astype(np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


def make_silent_wav(path: Path, seconds: float = 3.0) -> Path:
    audio = np.zeros(round(seconds * RATE), dtype=np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path: Path):
    s = Session(tmp_path / "MatchLoudness.kuulas")
    yield s
    s.close()


def test_match_loudness_three_tones_end_within_0_3_lu(session: Session, tmp_path: Path):
    w1 = make_tone_wav(tmp_path / "tone_m30.wav", -30.0)
    w2 = make_tone_wav(tmp_path / "tone_m20.wav", -20.0)
    w3 = make_tone_wav(tmp_path / "tone_m12.wav", -12.0)

    session.import_media([str(w1), str(w2), str(w3)])
    clips = [t.clips[0] for t in session.state.tracks]
    clip_ids = [c.id for c in clips]

    session.command("match_loudness", {"clip_ids": clip_ids, "target_lufs": -20.0})

    # Check report
    report = session.last_match_report
    assert len(report["matched"]) == 3
    assert len(report["skipped"]) == 0

    # Verify gains:
    for c_id in clip_ids:
        clip = session.state.clip(c_id)
        raw_lufs = measure_clip(session.store, clip, RATE)
        assert raw_lufs is not None
        effective_lufs = raw_lufs + clip.gain_db
        assert abs(effective_lufs - (-20.0)) <= 0.3


def test_silent_clip_skipped_and_reported(session: Session, tmp_path: Path):
    w1 = make_tone_wav(tmp_path / "tone.wav", -25.0)
    w2 = make_silent_wav(tmp_path / "silent.wav")

    session.import_media([str(w1), str(w2)])
    tone_clip = session.state.tracks[0].clips[0]
    silent_clip = session.state.tracks[1].clips[0]

    session.command(
        "match_loudness",
        {
            "clip_ids": [tone_clip.id, silent_clip.id],
            "target_lufs": -16.0,
        },
    )

    report = session.last_match_report
    matched_ids = [m[0] for m in report["matched"]]
    assert tone_clip.id in matched_ids
    assert silent_clip.id in report["skipped"]
    assert session.state.clip(silent_clip.id).gain_db == 0.0


def test_target_defaults_to_the_speech_role_target(session: Session, tmp_path: Path):
    w = make_tone_wav(tmp_path / "tone.wav", -26.0)
    session.import_media([str(w)])
    c_id = session.state.tracks[0].clips[0].id

    session.command("match_loudness", {"clip_ids": [c_id]})
    clip = session.state.clip(c_id)
    raw = measure_clip(session.store, clip, RATE)
    assert raw is not None
    effective = raw + clip.gain_db
    assert abs(effective - (-19.0)) <= 0.3  # WP49: was -16 before tracks had targets


def test_undo_restores_old_gains_and_redo_reapplies(session: Session, tmp_path: Path):
    w = make_tone_wav(tmp_path / "tone.wav", -26.0)
    session.import_media([str(w)])
    c_id = session.state.tracks[0].clips[0].id

    # Set initial gain
    session.edit("set_clip", {"clip_id": c_id, "gain_db": -2.0})
    assert session.state.clip(c_id).gain_db == -2.0

    session.command("match_loudness", {"clip_ids": [c_id], "target_lufs": -20.0})
    new_gain = session.state.clip(c_id).gain_db
    assert new_gain != -2.0

    session.undo()
    assert session.state.clip(c_id).gain_db == -2.0

    session.redo()
    assert session.state.clip(c_id).gain_db == new_gain


def test_session_lock_is_free_while_measuring(
    session: Session, tmp_path: Path, monkeypatch
):
    w = make_tone_wav(tmp_path / "tone.wav", -24.0)
    session.import_media([str(w)])
    c_id = session.state.tracks[0].clips[0].id

    free = []
    real_measure = sm.measure_clip

    def measure_with_probe(store, clip, rate, **kw):
        def try_lock():
            got = session.lock.acquire(timeout=1.0)
            if got:
                session.lock.release()
            free.append(got)

        other = threading.Thread(target=try_lock)
        other.start()
        other.join()
        return real_measure(store, clip, rate, **kw)

    monkeypatch.setattr(sm, "measure_clip", measure_with_probe)

    session.command("match_loudness", {"clip_ids": [c_id], "target_lufs": -20.0})
    assert free == [True]


def test_head_moved_concurrently_raises_error(
    session: Session, tmp_path: Path, monkeypatch
):
    w = make_tone_wav(tmp_path / "tone.wav", -24.0)
    session.import_media([str(w)])
    c_id = session.state.tracks[0].clips[0].id

    real_measure = sm.measure_clip

    def measure_and_mutate(store, clip, rate, **kw):
        # Concurrently perform an edit that advances the history head
        session.edit("add_track", {"name": "ConcurrentTrack"})
        return real_measure(store, clip, rate, **kw)

    monkeypatch.setattr(sm, "measure_clip", measure_and_mutate)

    with pytest.raises(ops.EditError) as exc_info:
        session.command("match_loudness", {"clip_ids": [c_id], "target_lufs": -20.0})

    assert exc_info.value.key == "error.session.concurrent_edit"


def test_command_response_carries_the_match_report(tmp_path: Path):
    class Engine:
        def status(self):
            return {"playing": False, "position": 0, "until": None, "notices": []}

        def close(self):
            pass

    s = Session(tmp_path / "Report.kuulas")
    loud = make_tone_wav(tmp_path / "loud.wav", -12.0)
    quiet = make_silent_wav(tmp_path / "quiet.wav")
    s.import_media([str(loud), str(quiet)])
    ids = [t.clips[0].id for t in s.state.tracks]
    ui = tmp_path / "ui"
    ui.mkdir()
    client = TestClient(create_app(s, Engine(), language="en", ui_dir=ui))
    body = client.post("/api/command",
                       json={"name": "match_loudness", "args": {"clip_ids": ids}}).json()
    assert [m["clip_id"] for m in body["match_report"]["matched"]] == [ids[0]]
    assert body["match_report"]["skipped"] == [ids[1]]
    s.close()
