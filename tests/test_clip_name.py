from __future__ import annotations

from pathlib import Path

import pytest

from kuulas import messages, ops
from kuulas.model import Clip, Media, Project, Track
from kuulas.session import Session


@pytest.fixture
def base_project() -> Project:
    p = Project(rate=48000)
    p = ops.add_media(
        p,
        Media(
            id="m1",
            name="voice.wav",
            channels=1,
            frames=96000,
            sha256="0123456789abcdef" * 4,
        ),
    )
    p = ops.add_track(p, track_id="t1", name="Dialogue")
    return ops.add_clip(p, "t1", "m1", clip_id="c1", start=0, offset=0, length=48000)


def test_clip_name_round_trip():
    c = Clip(
        id="c1",
        media="m1",
        start=0,
        offset=0,
        length=48000,
        name="Interview intro",
    )
    assert c.name == "Interview intro"

    d = c.to_dict()
    assert d["name"] == "Interview intro"

    c2 = Clip.from_dict(d)
    assert c2.name == "Interview intro"
    assert c2 == c


def test_legacy_clip_json_without_name_loads_cleanly():
    d = {
        "id": "c1",
        "media": "m1",
        "start": 0,
        "offset": 0,
        "length": 48000,
        "gain_db": 0.0,
        "pan": 0.0,
    }
    c = Clip.from_dict(d)
    assert c.name == ""


def test_api_project_state_clip_name():
    c_named = Clip(
        id="c1", media="m1", start=0, offset=0, length=48000, name="Intro"
    )
    c_unnamed = Clip(id="c2", media="m1", start=48000, offset=0, length=48000)

    d_named = c_named.to_dict()
    d_unnamed = c_unnamed.to_dict()

    assert d_named["name"] == "Intro"
    assert d_unnamed.get("name", "") == ""


def test_two_different_clips_can_have_the_same_name():
    c1 = Clip(id="c1", media="m1", start=0, offset=0, length=48000, name="Shared")
    c2 = Clip(
        id="c2", media="m1", start=48000, offset=0, length=48000, name="Shared"
    )
    assert c1.name == c2.name == "Shared"
    assert c1.id != c2.id

    p = Project(tracks=[Track(id="t1", name="Speech", clips=[c1, c2])])
    assert len(p.tracks[0].clips) == 2
    assert p.tracks[0].clips[0].name == "Shared"
    assert p.tracks[0].clips[1].name == "Shared"


def test_ops_set_clip_name_normalization(base_project: Project):
    # Leading and trailing spaces removed
    p = ops.set_clip(base_project, "c1", name="  Trimmed Name  ")
    assert p.tracks[0].clips[0].name == "Trimmed Name"

    # Truncated to 200 chars
    long_name = "A" * 250
    p = ops.set_clip(base_project, "c1", name=long_name)
    assert p.tracks[0].clips[0].name == "A" * 200
    assert len(p.tracks[0].clips[0].name) == 200

    # Whitespace only resets to empty (automatic)
    p = ops.set_clip(base_project, "c1", name="     ")
    assert p.tracks[0].clips[0].name == ""

    # Empty string resets to empty (automatic)
    p = ops.set_clip(base_project, "c1", name="Custom")
    assert p.tracks[0].clips[0].name == "Custom"
    p = ops.set_clip(p, "c1", name="")
    assert p.tracks[0].clips[0].name == ""


def test_ops_set_clips_updates_names(base_project: Project):
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="c2", start=48000, offset=0, length=48000
    )
    p2 = ops.set_clips(p, ["c1", "c2"], name="  Common  ")
    assert p2.tracks[0].clips[0].name == "Common"
    assert p2.tracks[0].clips[1].name == "Common"


def test_split_and_trim_preserve_name(base_project: Project):
    p = ops.set_clip(base_project, "c1", name="Story Piece")

    # Split
    p_split = ops.split_clip(p, "c1", at=24000)
    clips = p_split.tracks[0].clips
    assert len(clips) == 2
    assert clips[0].name == "Story Piece"
    assert clips[1].name == "Story Piece"

    # Trim
    p_trimmed = ops.trim_clip(p, "c1", start=1000, end=40000)
    assert p_trimmed.tracks[0].clips[0].name == "Story Piece"


def register(h, media_id: str, frames: int = 48000) -> None:
    h.db.execute(
        "insert into media(id, sha256, name, storage, channels, source_rate,"
        " source_frames, lossless, added_utc) values (?, ?, ?, 'working', 1, 48000,"
        " ?, 1, '2026-10-16T00:00:00Z')",
        (media_id, media_id * 4, media_id, frames),
    )


def test_session_rename_clip_undo_redo_and_locales(
    tmp_path: Path, base_project: Project
):
    s = Session(tmp_path / "RenameTest.kuulas")
    try:
        for m in base_project.media:
            register(s.history, m.id, m.frames)
        s.history.commit("init", base_project)

        # English label
        messages.set_language("en")
        label_en = messages.t("history.rename_clip")
        assert label_en == "Rename clip"

        s.edit("set_clip", {"clip_id": "c1", "name": "New Name"}, label=label_en)
        assert s.history.state.tracks[0].clips[0].name == "New Name"
        assert s.history.nodes()[-1]["label"] == "Rename clip"

        # Undo
        s.undo()
        assert s.history.state.tracks[0].clips[0].name == ""

        # Redo
        s.redo()
        assert s.history.state.tracks[0].clips[0].name == "New Name"

        # Finnish label
        messages.set_language("fi")
        label_fi = messages.t("history.rename_clip")
        assert label_fi == "Nimeä leike"
    finally:
        s.close()
        messages.set_language("en")
