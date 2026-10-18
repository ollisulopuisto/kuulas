"""Clip groups and merge (WP19a follow-up): reversible, one undo step each."""

from __future__ import annotations

import pytest

from kuulas import ops
from kuulas.model import Clip, Media, Project
from kuulas.session import Session

RATE = 48000


@pytest.fixture
def base() -> Project:
    p = ops.add_media(
        Project(rate=RATE),
        Media(id="m1", name="a.wav", channels=1, frames=10 * RATE, sha256="ab" * 32),
    )
    p = ops.add_media(
        p, Media(id="m2", name="b.wav", channels=1, frames=10 * RATE, sha256="cd" * 32)
    )
    p = ops.add_track(p, track_id="t1", name="A")
    return ops.add_track(p, track_id="t2", name="B")


def committed(s: Session, p: Project) -> None:
    """Make the session's project ``p`` (its media rows registered first)."""
    for m in p.media:
        s.history.db.execute(
            "insert into media(id, sha256, name, storage, channels, source_rate,"
            " source_frames, lossless, added_utc) values (?, ?, ?, 'working', 1, 48000,"
            " ?, 1, '2026-10-16T00:00:00Z')",
            (m.id, m.sha256, m.name, m.frames),
        )
    s.history.commit("setup", p)


def clips(p: Project, track: str = "t1") -> list[Clip]:
    return list(p.track(track).clips)


def group_of(p: Project, clip_id: str):
    return p.clip_and_track(clip_id)[0].group


def three(base: Project) -> Project:
    p = ops.add_clip(base, "t1", "m1", clip_id="c1", start=0, offset=0, length=1000)
    p = ops.add_clip(p, "t1", "m2", clip_id="c2", start=5000, offset=0, length=1000)
    return ops.add_clip(p, "t2", "m1", clip_id="c3", start=0, offset=0, length=1000)


# -- group ---------------------------------------------------------------------


def test_group_gives_the_clips_one_new_group_id(base):
    p = ops.group_clips(three(base), ["c1", "c2", "c3"])
    ids = {c.group for t in p.tracks for c in t.clips}
    assert len(ids) == 1
    assert ids != {None}
    assert ids != {""}


def test_ungrouped_clip_has_no_group_key_in_its_dict(base):
    p = three(base)
    assert "group" not in p.tracks[0].clips[0].to_dict()
    p = ops.group_clips(p, ["c1", "c2"])
    assert p.track("t1").clips[0].to_dict()["group"]


def test_group_needs_two_distinct_clips(base):
    p = three(base)
    with pytest.raises(ops.EditError) as e:
        ops.apply(p, "group_clips", {"clip_ids": ["c1"]})
    assert e.value.key == "error.edit.bad_arguments"
    with pytest.raises(ops.EditError):
        ops.group_clips(p, ["c1", "c1"])
    with pytest.raises(ops.EditError):
        ops.group_clips(p, [])


def test_group_unknown_clip_is_refused(base):
    with pytest.raises(ops.EditError):
        ops.group_clips(three(base), ["c1", "nope"])


def test_a_clip_in_another_group_leaves_it(base):
    p = ops.group_clips(three(base), ["c1", "c2"])
    old = group_of(p, "c2")
    p = ops.group_clips(p, ["c2", "c3"])
    assert group_of(p, "c1") == old
    assert group_of(p, "c2") == group_of(p, "c3")
    assert group_of(p, "c2") != old


def test_ungroup_clears_every_member_of_the_groups_of_the_listed_clips(base):
    p = ops.group_clips(three(base), ["c1", "c2", "c3"])
    p = ops.ungroup_clips(p, ["c1"])
    assert p == three(base)


def test_ungroup_leaves_other_groups_alone(base):
    p = ops.add_clip(three(base), "t2", "m2", clip_id="c4", start=3000, offset=0,
                     length=500)
    p = ops.group_clips(p, ["c1", "c2"])
    p = ops.group_clips(p, ["c3", "c4"])
    p = ops.ungroup_clips(p, ["c1"])
    assert group_of(p, "c3") is not None
    assert group_of(p, "c1") is None


def test_group_round_trips_through_the_dict_and_old_files_read_as_ungrouped(base):
    d = ops.group_clips(three(base), ["c1", "c2"]).tracks[0].clips[0].to_dict()
    assert Clip.from_dict(d).group == d["group"]
    del d["group"]
    assert Clip.from_dict(d).group is None


def test_split_keeps_the_group_on_both_halves(base):
    p = ops.group_clips(three(base), ["c1", "c2"])
    g = group_of(p, "c1")
    p = ops.split_clip(p, "c1", 400, new_id="c1b")
    assert group_of(p, "c1") == g
    assert group_of(p, "c1b") == g


def test_the_new_ops_are_whitelisted():
    for name in ("group_clips", "ungroup_clips", "merge_clips"):
        assert name in ops.OPS


def test_group_survives_save_and_reopen(tmp_path, base):
    folder = tmp_path / "G.kuulas"
    s = Session(folder)
    try:
        committed(s, three(base))
        s.edit("group_clips", {"clip_ids": ["c1", "c2"]})
        g = group_of(s.state, "c1")
        assert g
    finally:
        s.close()
    s = Session(folder)
    try:
        assert group_of(s.state, "c1") == g
        assert group_of(s.state, "c2") == g
        assert group_of(s.state, "c3") is None
    finally:
        s.close()


# -- merge ---------------------------------------------------------------------


def cut_three(base: Project) -> Project:
    p = ops.add_clip(base, "t1", "m1", clip_id="a", start=100, offset=50, length=3000)
    p = ops.split_clip(p, "a", 1100, new_id="b")
    return ops.split_clip(p, "b", 2100, new_id="c")


def test_merge_joins_contiguous_pieces_into_the_first_clip(base):
    p = ops.merge_clips(cut_three(base), ["a", "b", "c"])
    (only,) = clips(p)
    assert (only.id, only.start, only.offset, only.length) == ("a", 100, 50, 3000)


def test_merge_keeps_first_fade_in_last_fade_out_and_name(base):
    p = ops.add_clip(base, "t1", "m1", clip_id="a", start=0, offset=0, length=2000)
    p = ops.set_clip(p, "a", fade_in=100, fade_out=200, name="Intro")
    p = ops.split_clip(p, "a", 1000, new_id="b")
    (only,) = clips(ops.merge_clips(p, ["a", "b"]))
    assert (only.fade_in, only.fade_out, only.name) == (100, 200, "Intro")


def test_split_at_the_old_boundary_restores_the_clip_exactly(base):
    p = ops.add_clip(base, "t1", "m1", clip_id="a", start=100, offset=50, length=3000)
    p = ops.set_clip(p, "a", name="Intro", gain_db=-3.0)
    p = ops.add_clip(p, "t2", "m1", clip_id="z", start=0, offset=0, length=10)
    whole = ops.group_clips(p, ["a", "z"])
    cut = ops.split_clip(whole, "a", 1100, new_id="b")
    merged = ops.merge_clips(cut, ["a", "b"])
    assert merged == whole
    assert ops.split_clip(merged, "a", 1100, new_id="b") == cut


def test_merge_is_one_undo_step_with_equal_state(base, tmp_path):
    s = Session(tmp_path / "M.kuulas")
    try:
        committed(s, cut_three(base))
        before = s.state
        s.edit("merge_clips", {"clip_ids": ["a", "b", "c"]})
        assert len(clips(s.state)) == 1
        s.undo()
        assert s.state == before
        s.redo()
        assert len(clips(s.state)) == 1
        s.undo()
        assert s.state == before
    finally:
        s.close()


def test_merge_leaves_clips_that_cannot_join(base):
    p = ops.add_clip(cut_three(base), "t1", "m2", clip_id="x", start=3100, offset=0,
                     length=500)
    p = ops.merge_clips(p, ["a", "b", "x"])
    assert [c.id for c in clips(p)] == ["a", "c", "x"]
    assert clips(p)[0].length == 2000


def test_merge_only_touches_the_selection(base):
    p = ops.merge_clips(cut_three(base), ["a", "b"])
    assert [(c.id, c.length) for c in clips(p)] == [("a", 2000), ("c", 1000)]


def test_merge_with_nothing_joinable_is_refused(base):
    with pytest.raises(ops.EditError) as e:
        ops.merge_clips(three(base), ["c1", "c2", "c3"])
    assert e.value.key == "error.edit.merge_nothing"


def test_merge_works_per_track(base):
    p = ops.add_clip(cut_three(base), "t2", "m2", clip_id="d", start=0, offset=0,
                     length=1000)
    p = ops.split_clip(p, "d", 400, new_id="e")
    p = ops.merge_clips(p, ["a", "b", "c", "d", "e"])
    assert len(clips(p, "t1")) == 1
    assert len(clips(p, "t2")) == 1


def test_merged_clips_of_one_group_stay_grouped(base):
    p = ops.group_clips(cut_three(base), ["a", "b"])
    g = group_of(p, "a")
    p = ops.merge_clips(p, ["a", "b"])
    assert clips(p)[0].group == g


def test_merge_across_two_groups_is_refused_for_those_clips(base):
    p = ops.group_clips(cut_three(base), ["a", "c"])
    p = ops.group_clips(p, ["b", "c"])  # b and c share a group; a stays in the old one
    assert group_of(p, "a") != group_of(p, "b")
    with pytest.raises(ops.EditError) as e:
        ops.merge_clips(p, ["a", "b"])
    assert e.value.key == "error.edit.merge_nothing"
    assert len(clips(p)) == 3
