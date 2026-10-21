"""The clipboard preview never plays louder than the project (WP82)."""

import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import clipboard_level, mixer
from kuulas import session as session_module
from kuulas.model import Project
from kuulas.session import Session

RATE = 48000


def noise(path: Path, seed: int, amp: float) -> Path:
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(2 * RATE) * amp).astype(np.float32), RATE,
             subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "One.kuulas")
    s.import_media([str(noise(tmp_path / "a.wav", 1, 0.1)),
                    str(noise(tmp_path / "b.wav", 2, 0.1))])
    yield s
    s.close()


def set_all_clips(session, gain_db):
    for track in session.state.tracks:
        for clip in track.clips:
            session.edit("set_clip", {"clip_id": clip.id, "gain_db": gain_db})


def loud_entry_then_quiet_project(session, quiet_db=-20.0):
    """An entry copied at full level, then the project's own clips turned down."""
    a = session.state.tracks[0]
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    set_all_clips(session, quiet_db)
    return entry


def peak(project, session):
    mix = mixer.mix(project, session.store, 0, project.length)
    return float(np.abs(mix).max())


def test_a_louder_entry_is_attenuated_and_the_gain_is_reported(session):
    entry = loud_entry_then_quiet_project(session)
    project, missing, gain = session.clipboard_preview(entry)
    assert missing == 0
    assert gain == pytest.approx(-20.0, abs=1.5)
    assert project.master_gain_db == pytest.approx(gain)


def test_the_preview_is_not_louder_than_the_project(session):
    entry = loud_entry_then_quiet_project(session)
    project, _, _ = session.clipboard_preview(entry)
    own = max(peak(replace(session.state, tracks=(tr,)), session)
              for tr in session.state.tracks)
    assert peak(project, session) <= own * 1.5  # same level, give or take noise peaks


def test_an_entry_at_the_project_level_is_not_changed(session):
    a = session.state.tracks[0]
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    _, _, gain = session.clipboard_preview(entry)
    assert gain == pytest.approx(0.0, abs=1.5)


def test_a_quiet_entry_is_never_boosted(session):
    set_all_clips(session, -30.0)
    a = session.state.tracks[0]
    entry = session.clipboard_copy(clip_ids=[a.clips[0].id])["entry"]["id"]
    set_all_clips(session, 0.0)
    _, _, gain = session.clipboard_preview(entry)
    assert gain == 0.0


def test_switched_off_the_preview_is_untouched(session):
    entry = loud_entry_then_quiet_project(session)
    project, _, gain = session.clipboard_preview(entry, limit=False)
    assert gain == 0.0
    assert project.master_gain_db == 0.0


def test_the_project_is_not_changed(session):
    entry = loud_entry_then_quiet_project(session)
    before = session.state
    session.clipboard_preview(entry)
    assert session.state == before


def test_the_entry_is_measured_once(session, monkeypatch):
    entry = loud_entry_then_quiet_project(session)
    calls = []
    real = clipboard_level.entry_level
    monkeypatch.setattr(clipboard_level, "entry_level",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    session.clipboard_preview(entry)
    session.clipboard_preview(entry)
    assert len(calls) == 1


def test_an_empty_project_uses_the_default_reference():
    got = clipboard_level.project_reference(Project(rate=RATE), None, None)
    assert got == (-23.0, None)


def test_a_long_projects_reference_is_not_measured_while_the_click_waits(
        session, monkeypatch):
    # Owner, 2026-10-21: a clipboard preview sounded "VERY MUCH LATER". The request
    # measured every speech track of the project (the whole recording) before it
    # started the sound whenever that analysis was not cached yet, which it is not
    # while playback holds the background jobs back. Past a short project the
    # request uses the default reference and the measuring runs in the background.
    monkeypatch.setattr(session_module, "INLINE_REFERENCE_S", 0.1)
    entry = loud_entry_then_quiet_project(session)
    release = threading.Event()
    seen = []
    real = clipboard_level.project_reference

    def slow(*args):
        seen.append(threading.current_thread())
        release.wait(10)
        return real(*args)

    monkeypatch.setattr(clipboard_level, "project_reference", slow)
    began = time.perf_counter()
    project, _, gain = session.clipboard_preview(entry)
    assert time.perf_counter() - began < 1.0
    assert project is not None
    assert gain <= 0.0
    release.set()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if session.clipboard_preview(entry)[2] == pytest.approx(-20.0, abs=1.5):
            break
        time.sleep(0.05)
    else:
        pytest.fail("the background measuring never reached the preview level")
    assert seen
    assert all(t is not threading.main_thread() for t in seen)
