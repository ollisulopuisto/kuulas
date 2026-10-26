"""scripts/examples/remove_fillers.py is the spec of headless use (WP53): a script opens a
project, reads the transcript and removes the filler words with the same commands the UI
sends, with no LLM and no server. This runs it on a small synthetic project."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from test_history import register

from kuulas import ops
from kuulas.clock import FLICKS
from kuulas.model import Media, Project
from kuulas.session import Session

SCRIPT = (Path(__file__).resolve().parent.parent / "scripts" / "examples"
          / "remove_fillers.py")
RATE = 48_000
SECONDS = 8

# Olli says: Hei [Öö,] tämä [Um uh] jakso. The fillers have punctuation and capitals, and
# "Um uh" is two fillers side by side (one cut, not two).
WORDS = [("Hei", 0.0, 0.5), ("Öö,", 1.0, 1.4), ("tämä", 2.0, 2.5), ("Um", 3.0, 3.4),
         ("uh.", 3.5, 3.9), ("jakso", 5.0, 5.5)]


def load_script():
    spec = importlib.util.spec_from_file_location("remove_fillers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_project(tmp_path: Path) -> Session:
    """One speaker, one 8 s clip, and the words above as its transcript (no audio file is
    needed: the words and the clip are all the example reads)."""
    frames = SECONDS * RATE
    project = Project(rate=RATE)
    project = ops.add_media(
        project,
        Media(id="ma", name="olli.wav", channels=1, frames=frames, sha256="ma" * 32))
    project = ops.add_track(project, track_id="t1", name="Olli")
    project = ops.add_clip(project, "t1", "ma", start=0, clip_id="c1")
    session = Session(tmp_path / "Episode.kuulas")
    register(session.history, "ma", frames)
    session.history.commit("fixture", project)
    session.history.add_transcript("ma", [
        {"w": w, "s": int(start * FLICKS), "e": int(end * FLICKS), "spk": "Olli"}
        for w, start, end in WORDS])
    return session


def spoken(session: Session) -> list[str]:
    return [w["w"] for w in session.heard_words()]


def test_the_fixture_has_the_words_it_says(tmp_path):
    session = make_project(tmp_path)
    try:
        assert spoken(session) == [w for w, _, _ in WORDS]
    finally:
        session.close()


def test_finding_fillers_ignores_case_and_punctuation_and_changes_nothing(tmp_path):
    script = load_script()
    session = make_project(tmp_path)
    try:
        before = session.state.to_dict()
        assert script.find_fillers(session.heard_words()) == [1, 3, 4]
        assert session.state.to_dict() == before
    finally:
        session.close()


def test_removing_fillers_cuts_each_run_once_and_leaves_the_rest(tmp_path):
    script = load_script()
    session = make_project(tmp_path)
    try:
        length = session.state.length
        done = script.remove_fillers(session)
        assert done == {"words": 3, "cuts": 2}
        assert spoken(session) == ["Hei", "tämä", "jakso"]
        assert session.state.length < length
    finally:
        session.close()


def test_each_cut_is_one_undo_step(tmp_path):
    script = load_script()
    session = make_project(tmp_path)
    try:
        original = session.state.to_dict()
        script.remove_fillers(session)
        session.undo()
        session.undo()
        assert session.state.to_dict() == original
        assert spoken(session) == [w for w, _, _ in WORDS]
    finally:
        session.close()


def test_a_project_with_no_fillers_is_left_alone(tmp_path):
    script = load_script()
    session = make_project(tmp_path)
    try:
        script.remove_fillers(session)
        steps = session.state.to_dict()
        assert script.remove_fillers(session) == {"words": 0, "cuts": 0}
        assert session.state.to_dict() == steps
    finally:
        session.close()


def test_the_command_line_lists_with_dry_run_and_then_removes(tmp_path, capsys):
    script = load_script()
    make_project(tmp_path).close()
    folder = str(tmp_path / "Episode.kuulas")
    assert script.main([folder, "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == "3 filler words: Öö,, Um, uh."
    assert script.main([folder]) == 0
    assert capsys.readouterr().out.strip() == "Removed 3 filler words in 2 cuts."
    session = Session(folder)
    try:
        assert spoken(session) == ["Hei", "tämä", "jakso"]
    finally:
        session.close()
