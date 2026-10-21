"""The rendered mix remembered (``mix_done.render``) and whether it still matches the
edit: the audio-state key (``export.audio_key``), the file's presence and size.

No audio playback; the automixer is a fake (see test_automix_range.py)."""

import sys
import textwrap
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import automix, export, messages, ops, render_listen
from kuulas.model import Bus, Media, Project
from kuulas.session import Session

RATE = 48000


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


def noise(path: Path, seconds: float, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    audio = (rng.standard_normal(round(seconds * RATE)) * 0.1).astype(np.float32)
    sf.write(path, audio, RATE, subtype="PCM_16")
    return path


@pytest.fixture
def session(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir()
    s.import_media([str(noise(src / "Olli.wav", 3, 1)),
                    str(noise(src / "Maija.wav", 3, 2))])
    yield s
    s.close()


def rendered(session, tmp_path, *, rng=None, frames=4800) -> Path:
    """A mix file as the automixer would leave it, and the run's result noted."""
    path = tmp_path / ("mix preview.wav" if rng else "mix.wav")
    sf.write(path, np.zeros((frames, 2), dtype=np.float32), RATE, subtype="PCM_24")
    session.note_render({"path": str(path), "name": path.name, "range": rng,
                         "edit_key": export.audio_key(session.state),
                         "frames": frames, "rate": RATE})
    return path


# -- the audio-state key ---------------------------------------------------------------


def base_project() -> Project:
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m1", name="a.wav", channels=1, frames=RATE * 4,
                               sha256="aa"))
    p = ops.add_track(p, "t1", "m1")
    p = ops.add_clip(p, "t1", "m1", start=0, clip_id="c1", length=RATE)
    return replace(p, buses=(Bus(id="b1", name="Bus"),))


def same(p: Project, q: Project) -> bool:
    return export.audio_key(p) == export.audio_key(q)


@pytest.mark.parametrize("change", [
    lambda p: ops.add_marker(p, None, "Intro", 100),
    lambda p: ops.set_track(p, "t1", name="Olli"),
    lambda p: ops.set_clip(p, "c1", name="first"),
    lambda p: ops.set_bus(p, "b1", name="Voices"),
    lambda p: replace(p, mix_done={"bed_level": {"offset_db": -3}}),
    lambda p: replace(p, media=tuple(replace(m, name="renamed.wav") for m in p.media)),
])
def test_names_markers_and_records_do_not_change_the_key(change):
    p = base_project()
    assert same(p, change(p))


@pytest.mark.parametrize("change", [
    lambda p: ops.set_clip(p, "c1", gain_db=-3.0),
    lambda p: ops._replace_clip(p, replace(p.clip("c1"), offset=10)),
    lambda p: ops.set_clip(p, "c1", muted=True),
    lambda p: ops.move_clip(p, "c1", 500),
    lambda p: ops.set_track(p, "t1", gain_db=2.0),
    lambda p: ops.set_track(p, "t1", mute=True),
    lambda p: ops.set_track(p, "t1", kind="music"),
    lambda p: ops.set_track(p, "t1", bus="b1"),
    lambda p: ops.set_gate(p, "t1", [[0, 100]]),
    lambda p: ops.set_track_automation(p, "t1", [[0, -6.0]]),
    lambda p: ops.set_bus(p, "b1", gain_db=-4.0),
    lambda p: ops.set_bus(p, "b1", kind="music"),
    lambda p: ops.set_master(p, -1.0),
    lambda p: replace(p, media=tuple(replace(m, sha256="bb") for m in p.media)),
    lambda p: replace(p, rate=44100),
])
def test_edits_that_change_the_sound_change_the_key(change):
    p = base_project()
    assert not same(p, change(p))


# -- the record ----------------------------------------------------------------------


def test_note_render_records_the_file_and_is_current(session, tmp_path):
    path = rendered(session, tmp_path)
    entry = session.state.mix_done["render"]
    assert entry["path"] == str(path)
    assert entry["name"] == "mix.wav"
    assert entry["range"] is None
    assert entry["frames"] == 4800
    assert entry["rate"] == RATE
    assert entry["size"] == path.stat().st_size
    assert entry["set_at"].endswith(("+03:00", "+02:00", "+00:00", "Z")) or "+" in entry[
        "set_at"]
    assert render_listen.render_current(session.state) == entry
    info = render_listen.status(session.state)
    assert info == {"available": True, "current": True, "missing": False,
                    "name": "mix.wav", "range": None, "set_at": entry["set_at"],
                    "reason": None}


def test_no_record_is_no_render(session):
    assert render_listen.render_current(session.state) is None
    assert render_listen.status(session.state)["available"] is False


def test_an_edit_that_changes_the_sound_makes_it_stale_and_undo_brings_it_back(
        session, tmp_path):
    rendered(session, tmp_path)
    track = session.state.tracks[0]
    session.edit("set_track", {"track_id": track.id, "gain_db": -2.0})
    assert render_listen.render_current(session.state) is None
    info = render_listen.status(session.state)
    # The record stays: the user can see there is an older render.
    assert info["available"] is True
    assert info["current"] is False
    assert info["reason"] == "edited"
    session.undo()
    assert render_listen.status(session.state)["current"] is True


def test_markers_and_names_keep_it_current(session, tmp_path):
    rendered(session, tmp_path)
    track = session.state.tracks[0]
    session.edit("set_track", {"track_id": track.id, "name": "Host"})
    session.edit("add_marker", {"marker_id": None, "name": "Intro", "start": 100})
    assert render_listen.status(session.state)["current"] is True


def test_a_missing_or_changed_file_is_not_current_and_is_never_deleted(session, tmp_path):
    path = rendered(session, tmp_path)
    sf.write(path, np.zeros((9000, 2), dtype=np.float32), RATE, subtype="PCM_24")
    info = render_listen.status(session.state)
    assert info["current"] is False
    assert info["reason"] == "changed"
    path.unlink()
    info = render_listen.status(session.state)
    assert info == {**info, "available": True, "current": False, "missing": True,
                    "reason": "missing"}


def test_a_range_render_is_remembered_with_its_range(session, tmp_path):
    rendered(session, tmp_path, rng=[RATE, 2 * RATE])
    assert render_listen.status(session.state)["range"] == [RATE, 2 * RATE]


def test_noting_a_render_is_its_own_undo_step_that_changes_no_sound(session, tmp_path):
    before = export.audio_key(session.state)
    rendered(session, tmp_path)
    assert export.audio_key(session.state) == before
    assert session.history.can_undo


FAKE = textwrap.dedent('''
    import sys
    import numpy as np, soundfile as sf
    argv = sys.argv[1:]
    out = argv[argv.index("-o") + 1]
    sf.write(out, np.zeros((4800, 2), dtype="float32"), 48000, subtype="PCM_24")
    print("PROGRESS 100 done", flush=True)
''')


def test_a_finished_automix_job_remembers_its_render(session, tmp_path, monkeypatch):
    script = tmp_path / "fake_automixer.py"
    script.write_text(FAKE, encoding="utf-8")
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    automix.save_settings({"command": [sys.executable, str(script)], "cwd": str(tmp_path),
                           "extra_args": []})
    key = export.audio_key(session.state)
    [job_id] = session.automix({"range": [RATE, 2 * RATE]})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert job["state"] == "completed", job
    entry = session.state.mix_done["render"]
    assert entry["path"] == job["result"]["path"]
    assert entry["range"] == [RATE, 2 * RATE]
    assert entry["edit_key"] == key
    assert entry["frames"] == 4800
    assert render_listen.status(session.state)["current"] is True
