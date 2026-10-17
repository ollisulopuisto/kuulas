from __future__ import annotations

from pathlib import Path

import pytest

from kuulas import ops
from kuulas.model import Clip, Media, Project, Track
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
    return ops.add_track(p, track_id="t1", name="Speech")


def test_muted_middle_piece_restored_joins_into_one_clip(base_project: Project):
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="c1", start=0, offset=0, length=48000
    )
    # Split into 3 pieces: 0..10000, 10000..30000, 30000..48000
    p = ops.split_clip(p, "c1", at=10000, new_id="c_mid")
    p = ops.split_clip(p, "c_mid", at=30000, new_id="c_right")
    # Mute the middle piece
    p = ops.set_clip(p, "c_mid", muted=True)
    assert len(p.tracks[0].clips) == 3
    assert p.tracks[0].clips[1].muted is True

    # Restore the cut
    p2 = ops.restore_cuts(p, ["c_mid"])
    clips = p2.tracks[0].clips
    assert len(clips) == 1
    assert clips[0].id == "c1"
    assert clips[0].start == 0
    assert clips[0].offset == 0
    assert clips[0].length == 48000
    assert clips[0].muted is False


def test_two_unrelated_adjacent_split_clips_elsewhere_on_track_stay_split(
    base_project: Project,
):
    # Unrelated intentional split clips at start of track: u1, u2
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="u1", start=0, offset=0, length=20000
    )
    p = ops.split_clip(p, "u1", at=10000, new_id="u2")
    assert len(p.tracks[0].clips) == 2

    # Later on the same track, a soft cut: c1 split and middle muted
    p = ops.add_clip(
        p, "t1", "m1", clip_id="c1", start=30000, offset=30000, length=30000
    )
    p = ops.split_clip(p, "c1", at=40000, new_id="c_mid")
    p = ops.split_clip(p, "c_mid", at=50000, new_id="c_right")
    p = ops.set_clip(p, "c_mid", muted=True)
    assert len(p.tracks[0].clips) == 5

    # Restore only c_mid
    p2 = ops.restore_cuts(p, ["c_mid"])
    clips = p2.tracks[0].clips
    # u1 and u2 must stay separate; c1, c_mid, c_right join into 1
    assert len(clips) == 3
    assert [c.id for c in clips] == ["u1", "u2", "c1"]
    assert clips[0].length == 10000
    assert clips[1].length == 10000
    assert clips[2].length == 30000


def test_restoring_two_cuts_on_one_track_joins_each_group_separately(
    base_project: Project,
):
    # Cut A: a1 (0..5000), a_mid (5000..10000, muted), a2 (10000..15000)
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="a1", start=0, offset=0, length=15000
    )
    p = ops.split_clip(p, "a1", at=5000, new_id="a_mid")
    p = ops.split_clip(p, "a_mid", at=10000, new_id="a2")
    p = ops.set_clip(p, "a_mid", muted=True)

    # In between: intentional split clips u1 (20000..25000), u2 (25000..30000)
    p = ops.add_clip(
        p, "t1", "m1", clip_id="u1", start=20000, offset=20000, length=10000
    )
    p = ops.split_clip(p, "u1", at=25000, new_id="u2")

    # Cut B: b1 (35000..40000), b_mid (40000..45000, muted), b2 (45000..50000)
    p = ops.add_clip(
        p, "t1", "m1", clip_id="b1", start=35000, offset=35000, length=15000
    )
    p = ops.split_clip(p, "b1", at=40000, new_id="b_mid")
    p = ops.split_clip(p, "b_mid", at=45000, new_id="b2")
    p = ops.set_clip(p, "b_mid", muted=True)

    assert len(p.tracks[0].clips) == 8

    # Restore both cuts simultaneously
    p2 = ops.restore_cuts(p, ["a_mid", "b_mid"])
    clips = p2.tracks[0].clips
    assert len(clips) == 4
    assert [c.id for c in clips] == ["a1", "u1", "u2", "b1"]
    assert clips[0].length == 15000
    assert clips[1].length == 5000
    assert clips[2].length == 5000
    assert clips[3].length == 15000


def test_clips_on_other_tracks_are_untouched(base_project: Project):
    # Track 1 has cut
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="c1", start=0, offset=0, length=30000
    )
    p = ops.split_clip(p, "c1", at=10000, new_id="c_mid")
    p = ops.set_clip(p, "c_mid", muted=True)

    # Track 2 has adjacent split clips
    p = ops.add_track(p, track_id="t2", name="Music")
    p = ops.add_clip(p, "t2", "m1", clip_id="t2_c1", start=0, offset=0, length=20000)
    p = ops.split_clip(p, "t2_c1", at=10000, new_id="t2_c2")
    assert len(p.tracks[1].clips) == 2

    p2 = ops.restore_cuts(p, ["c_mid"])
    # Track 1 joined
    assert len(p2.tracks[0].clips) == 1
    # Track 2 completely unchanged
    assert len(p2.tracks[1].clips) == 2
    assert [c.id for c in p2.tracks[1].clips] == ["t2_c1", "t2_c2"]


def test_different_gain_does_not_join(base_project: Project):
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="c1", start=0, offset=0, length=30000
    )
    p = ops.split_clip(p, "c1", at=10000, new_id="c_mid")
    p = ops.set_clip(p, "c_mid", muted=True, gain_db=-6.0)

    p2 = ops.restore_cuts(p, ["c_mid"])
    clips = p2.tracks[0].clips
    # c_mid is unmuted, but different gain prevents join
    assert len(clips) == 2
    assert clips[0].muted is False
    assert clips[1].muted is False
    assert clips[1].gain_db == -6.0


def test_different_pan_does_not_join(base_project: Project):
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="c1", start=0, offset=0, length=30000
    )
    p = ops.split_clip(p, "c1", at=10000, new_id="c_mid")
    p = ops.set_clip(p, "c_mid", muted=True, pan=0.5)

    p2 = ops.restore_cuts(p, ["c_mid"])
    clips = p2.tracks[0].clips
    assert len(clips) == 2
    assert clips[1].pan == 0.5


def test_envelope_blocks_join(base_project: Project):
    p = ops.add_clip(
        base_project, "t1", "m1", clip_id="c1", start=0, offset=0, length=30000
    )
    p = ops.split_clip(p, "c1", at=10000, new_id="c_mid")
    p = ops.set_clip(p, "c_mid", muted=True)
    p = ops.set_clip_envelope(p, "c1", [(0, 0.0), (5000, -3.0)])

    p2 = ops.restore_cuts(p, ["c_mid"])
    clips = p2.tracks[0].clips
    assert len(clips) == 2


def test_crossfades_at_join_block_join(base_project: Project):
    # Two clips with xfade at boundary
    c1 = Clip(id="c1", media="m1", start=0, offset=0, length=10000, xfade_out=100)
    c2 = Clip(id="c2", media="m1", start=10000, offset=10000, length=10000, muted=True)
    track = Track(id="t1", name="S", clips=[c1, c2])
    p = Project(rate=48000, media=base_project.media, tracks=[track])

    p2 = ops.restore_cuts(p, ["c2"])
    clips = p2.tracks[0].clips
    assert len(clips) == 2


def test_non_contiguous_timeline_or_source_does_not_join(base_project: Project):
    # Timeline gap
    c1 = Clip(id="c1", media="m1", start=0, offset=0, length=10000)
    c2 = Clip(id="c2", media="m1", start=12000, offset=10000, length=10000, muted=True)
    track = Track(id="t1", name="S", clips=[c1, c2])
    p = Project(rate=48000, media=base_project.media, tracks=[track])

    p2 = ops.restore_cuts(p, ["c2"])
    clips = p2.tracks[0].clips
    assert len(clips) == 2

    # Source gap
    c3 = Clip(id="c3", media="m1", start=0, offset=0, length=10000)
    c4 = Clip(id="c4", media="m1", start=10000, offset=15000, length=10000, muted=True)
    track_src = Track(id="t1", name="S", clips=[c3, c4])
    p_src = Project(rate=48000, media=base_project.media, tracks=[track_src])
    p2_src = ops.restore_cuts(p_src, ["c4"])
    assert len(p2_src.tracks[0].clips) == 2


def test_session_restore_cuts_undo_redo(tmp_path: Path, base_project: Project):
    s = Session(tmp_path / "RestoreCut.kuulas")
    try:
        register(s.history, "m1", 96000)
        p = ops.add_clip(
            base_project, "t1", "m1", clip_id="c1", start=0, offset=0, length=48000
        )
        p = ops.split_clip(p, "c1", at=10000, new_id="c_mid")
        p = ops.split_clip(p, "c_mid", at=30000, new_id="c_right")
        p = ops.set_clip(p, "c_mid", muted=True)
        s.history.commit("soft cut", p)

        assert len(s.history.state.tracks[0].clips) == 3

        # Execute restore_cuts via session.edit
        s.edit("restore_cuts", {"clip_ids": ["c_mid"]})
        assert len(s.history.state.tracks[0].clips) == 1
        assert s.history.state.tracks[0].clips[0].length == 48000

        # Undo restores the 3 pieces with middle muted
        s.undo()
        clips = s.history.state.tracks[0].clips
        assert len(clips) == 3
        assert clips[1].id == "c_mid"
        assert clips[1].muted is True

        # Redo merges again
        s.redo()
        assert len(s.history.state.tracks[0].clips) == 1
    finally:
        s.close()
