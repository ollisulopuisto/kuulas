from __future__ import annotations

from pathlib import Path

import pytest

from kuulas import ops
from kuulas.model import Media, Project
from kuulas.session import Session


def register(h, media_id: str, frames: int = 96000) -> None:
    h.db.execute(
        "insert into media(id, sha256, name, storage, channels, source_rate,"
        " source_frames, lossless, added_utc) values (?, ?, ?, 'working', 1, 48000,"
        " ?, 1, '2026-10-16T00:00:00Z')",
        (media_id, media_id * 4, media_id, frames),
    )


@pytest.fixture
def base_project() -> Project:
    p = Project(rate=48000)
    p = ops.add_media(
        p,
        Media(
            id="m1",
            name="audio.wav",
            channels=1,
            frames=96000,
            sha256="0123456789abcdef" * 4,
        ),
    )
    p = ops.add_track(p, track_id="t1", name="Speech")
    return ops.add_clip(
        p, "t1", "m1", clip_id="c1", start=100, offset=0, length=100
    )


def test_nearer_end_closer_to_start_picks_fade_in(base_project: Project):
    # Clip: start=100, length=100, end=200
    # frame=120: dist to start=20, dist to end=80 -> nearer to start -> fade_in=20
    p = ops.set_fade_at(base_project, "c1", 120)
    clip = p.clip("c1")
    assert clip.fade_in == 20
    assert clip.fade_out == 0


def test_nearer_end_closer_to_end_picks_fade_out(base_project: Project):
    # frame=180: dist to start=80, dist to end=20 -> nearer to end -> fade_out=20
    p = ops.set_fade_at(base_project, "c1", 180)
    clip = p.clip("c1")
    assert clip.fade_in == 0
    assert clip.fade_out == 20


def test_nearer_end_midpoint_picks_fade_in(base_project: Project):
    # frame=150: dist to start=50, dist to end=50 -> equidistant -> fade_in=50
    p = ops.set_fade_at(base_project, "c1", 150)
    clip = p.clip("c1")
    assert clip.fade_in == 50
    assert clip.fade_out == 0


def test_explicit_side_in(base_project: Project):
    # frame=180 with explicit side="in" -> fade_in=80
    p = ops.set_fade_at(base_project, "c1", 180, side="in")
    clip = p.clip("c1")
    assert clip.fade_in == 80
    assert clip.fade_out == 0

    # Also accept "fade_in"
    p2 = ops.set_fade_at(base_project, "c1", 180, side="fade_in")
    clip2 = p2.clip("c1")
    assert clip2.fade_in == 80
    assert clip2.fade_out == 0


def test_explicit_side_out(base_project: Project):
    # frame=120 with explicit side="out" -> fade_out=80
    p = ops.set_fade_at(base_project, "c1", 120, side="out")
    clip = p.clip("c1")
    assert clip.fade_in == 0
    assert clip.fade_out == 80

    # Also accept "fade_out"
    p2 = ops.set_fade_at(base_project, "c1", 120, side="fade_out")
    clip2 = p2.clip("c1")
    assert clip2.fade_in == 0
    assert clip2.fade_out == 80


def test_explicit_side_invalid_raises(base_project: Project):
    with pytest.raises(ops.EditError):
        ops.set_fade_at(base_project, "c1", 120, side="invalid")


def test_clamping_at_boundaries(base_project: Project):
    # frame at exact clip.start (100) -> fade_in=0
    p = ops.set_fade_at(base_project, "c1", 100, side="in")
    clip = p.clip("c1")
    assert clip.fade_in == 0


def test_clip_of_length_one(base_project: Project):
    # Clip of length 1: start=10, length=1, end=11
    p = ops.add_clip(base_project, "t1", "m1", clip_id="c_single", start=10, length=1)
    # At frame=10, side="out": fade_out clamped to 1, other fade shortened to 0
    p1 = ops.set_fade_at(p, "c_single", 10, side="out")
    c1 = p1.clip("c_single")
    assert c1.fade_out == 1
    assert c1.fade_in == 0

    # At frame=10, side="in": fade_in=0, fade_out=0
    p2 = ops.set_fade_at(p, "c_single", 10, side="in")
    c2 = p2.clip("c_single")
    assert c2.fade_in == 0
    assert c2.fade_out == 0


def test_overlap_shortens_other_fade(base_project: Project):
    # Set existing fade_out=40
    p = ops.set_clip(base_project, "c1", fade_out=40)
    # Setting fade_in at frame=170 -> new_fade_in = 70.
    # Sum: 70 + 40 = 110 > 100 -> fade_out shortened to 30.
    p1 = ops.set_fade_at(p, "c1", 170, side="in")
    c1 = p1.clip("c1")
    assert c1.fade_in == 70
    assert c1.fade_out == 30

    # Now setting fade_out at frame=120 -> new_fade_out = 80.
    # Sum: 70 + 80 = 150 > 100 -> fade_in shortened to 20.
    p2 = ops.set_fade_at(p1, "c1", 120, side="out")
    c2 = p2.clip("c1")
    assert c2.fade_in == 20
    assert c2.fade_out == 80


def test_frame_outside_clip_raises(base_project: Project):
    # Clip: [100, 200)
    with pytest.raises(ops.EditError) as exc_before:
        ops.set_fade_at(base_project, "c1", 99)
    assert exc_before.value.key == "error.edit.split_outside"

    with pytest.raises(ops.EditError) as exc_at_end:
        ops.set_fade_at(base_project, "c1", 200)
    assert exc_at_end.value.key == "error.edit.split_outside"

    with pytest.raises(ops.EditError) as exc_past_end:
        ops.set_fade_at(base_project, "c1", 250)
    assert exc_past_end.value.key == "error.edit.split_outside"


def test_unknown_clip_raises(base_project: Project):
    with pytest.raises(ops.EditError) as exc:
        ops.set_fade_at(base_project, "nonexistent", 120)
    assert exc.value.key == "error.edit.no_clip"


def test_session_edit_undo_redo(tmp_path: Path, base_project: Project):
    s = Session(tmp_path / "FadeAt.kuulas")
    try:
        register(s.history, "m1", 96000)
        s.history.commit("init", base_project)

        # Apply set_fade_at via session.edit
        s.edit("set_fade_at", {"clip_id": "c1", "frame": 120})
        clip = s.history.state.clip("c1")
        assert clip.fade_in == 20
        assert clip.fade_out == 0

        # Undo restores original
        s.undo()
        clip_undone = s.history.state.clip("c1")
        assert clip_undone.fade_in == 0
        assert clip_undone.fade_out == 0

        # Redo reapplies
        s.redo()
        clip_redone = s.history.state.clip("c1")
        assert clip_redone.fade_in == 20
        assert clip_redone.fade_out == 0
    finally:
        s.close()


def test_old_project_loads(base_project: Project):
    d = base_project.to_dict()
    # Existing serialization format
    loaded = Project.from_dict(d)
    p = ops.set_fade_at(loaded, "c1", 130)
    assert p.clip("c1").fade_in == 30
