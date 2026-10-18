"""Importing onto an existing track (owner, 2026-10-19): more than one file on the same
track, and onto the track that is selected, whether it was made first or not."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import messages, ops
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Talk.kuulas")
    yield s
    s.close()


def wav(path: Path, seconds: float, seed: int = 0) -> str:
    rng = np.random.default_rng(seed)
    data = (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32)
    sf.write(path, data, RATE, subtype="PCM_16")
    return str(path)


def clips_of(session, track_id):
    track = next(t for t in session.state.tracks if t.id == track_id)
    return sorted((c.start, c.end) for c in track.clips)


def test_files_land_one_after_another_on_the_given_track(session, tmp_path):
    session.edit("add_track", {"track_id": "T", "name": "Music", "kind": "music"})
    a = wav(tmp_path / "a.wav", 2.0, 1)
    b = wav(tmp_path / "b.wav", 3.0, 2)
    session.import_media([a, b], onto_track="T", start_frame=5 * RATE)
    assert [t.id for t in session.state.tracks] == ["T"]  # no new track
    assert clips_of(session, "T") == [(5 * RATE, 7 * RATE), (7 * RATE, 10 * RATE)]


def test_an_unknown_track_is_an_error_and_nothing_changes(session, tmp_path):
    a = wav(tmp_path / "a.wav", 1.0)
    before = session.state
    with pytest.raises(ops.EditError):
        session.import_media([a], onto_track="nope")
    assert session.state == before


def test_without_a_track_the_import_makes_its_own_as_before(session, tmp_path):
    a = wav(tmp_path / "a.wav", 1.0, 1)
    b = wav(tmp_path / "b.wav", 1.0, 2)
    session.import_media([a, b])
    assert len(session.state.tracks) == 2


def test_one_undo_step_and_the_step_replays_with_the_track(session, tmp_path):
    session.edit("add_track", {"track_id": "T", "name": "Music", "kind": "music"})
    a = wav(tmp_path / "a.wav", 1.0, 1)
    session.import_media([a], onto_track="T")
    assert session.history.can_undo
    session.undo()
    assert clips_of(session, "T") == []
