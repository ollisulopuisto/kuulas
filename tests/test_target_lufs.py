"""Track.target_lufs (WP49): role defaults, edit, save, undo, match_loudness."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import ops, package
from kuulas.loudness import default_target_lufs, measure_clip
from kuulas.model import Project, Track
from kuulas.session import Session

RATE = 48000


def tone(path: Path, lufs: float, seconds: float = 3.0) -> Path:
    t = np.linspace(0, seconds, round(seconds * RATE), endpoint=False)
    amp = 10 ** ((lufs + 3.01) / 20)
    sf.write(path, (amp * np.sin(2 * np.pi * 1000 * t)).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "T.kuulas")
    yield s
    s.close()


def test_role_defaults():
    assert default_target_lufs("speech") == -19.0
    assert default_target_lufs("music") == -23.0
    assert default_target_lufs("narration") == -19.0
    assert default_target_lufs("speech-mix") == -19.0
    assert default_target_lufs("nonsense") is None


def test_track_without_target_keeps_its_bytes():
    assert "target_lufs" not in Track(id="t", name="A").to_dict()


def test_track_target_round_trips_through_dict():
    t = Track(id="t", name="A", target_lufs=-21.5)
    assert Track.from_dict(t.to_dict()).target_lufs == -21.5


def test_set_track_target_and_clear():
    p = ops.add_track(Project(), track_id="t", name="A")
    p = ops.set_track(p, "t", target_lufs=-20)
    assert p.track("t").target_lufs == -20.0
    p = ops.set_track(p, "t", target_lufs=None)
    assert p.track("t").target_lufs is None


@pytest.mark.parametrize("bad", ["loud", float("nan"), float("inf"), 5.0, -200.0])
def test_set_track_rejects_bad_target(bad):
    p = ops.add_track(Project(), track_id="t", name="A")
    with pytest.raises(ops.EditError):
        ops.set_track(p, "t", target_lufs=bad)


def test_target_survives_save_reopen_and_undo(tmp_path):
    folder = tmp_path / "P.kuulas"
    s = Session(folder)
    s.edit("add_track", {"track_id": "t", "name": "A"})
    s.edit("set_track", {"track_id": "t", "target_lufs": -21.0})
    s.undo()
    assert s.state.track("t").target_lufs is None
    s.redo()
    s.close()
    again = package.open_package(folder)
    assert again.history.state.track("t").target_lufs == -21.0
    again.close()


def test_match_loudness_without_target_uses_the_role_default(session, tmp_path):
    session.import_media([str(tone(tmp_path / "a.wav", -30.0))])
    track = session.state.tracks[0]
    cid = track.clips[0].id
    session.command("match_loudness", {"clip_ids": [cid]})
    clip = session.state.clip(cid)
    raw = measure_clip(session.store, clip, RATE)
    assert abs(raw + clip.gain_db - default_target_lufs(track.kind)) <= 0.3


def test_match_loudness_prefers_the_track_target(session, tmp_path):
    session.import_media([str(tone(tmp_path / "a.wav", -30.0))])
    track = session.state.tracks[0]
    cid = track.clips[0].id
    session.edit("set_track", {"track_id": track.id, "target_lufs": -25.0})
    session.command("match_loudness", {"clip_ids": [cid]})
    clip = session.state.clip(cid)
    raw = measure_clip(session.store, clip, RATE)
    assert abs(raw + clip.gain_db - (-25.0)) <= 0.3


def test_explicit_argument_still_wins(session, tmp_path):
    session.import_media([str(tone(tmp_path / "a.wav", -30.0))])
    track = session.state.tracks[0]
    cid = track.clips[0].id
    session.edit("set_track", {"track_id": track.id, "target_lufs": -25.0})
    session.command("match_loudness", {"clip_ids": [cid], "target_lufs": -20.0})
    clip = session.state.clip(cid)
    raw = measure_clip(session.store, clip, RATE)
    assert abs(raw + clip.gain_db - (-20.0)) <= 0.3
