"""Dragging a clip edge: roll_trim (cut point moves), ripple_trim (rest follows)."""

import pytest

from kuulas import ops
from kuulas.model import Media, Project

RATE = 48000
S = RATE


def project() -> Project:
    """Track A: a (2-6 s, source 2-6 s of 10) and b, muted (6-9 s, source 6-9 s).
    Track B: c (1-3 s) and d (7-9 s, source from 0). A marker at 8 s."""
    p = Project(rate=RATE)
    for m in ("m1", "m2"):
        p = ops.add_media(p, Media(id=m, name=f"{m}.wav", channels=1, frames=10 * S))
    p = ops.add_track(p, track_id="A", name="A")
    p = ops.add_track(p, track_id="B", name="B")
    p = ops.add_clip(p, "A", "m1", start=2 * S, offset=2 * S, length=4 * S, clip_id="a")
    p = ops.add_clip(p, "A", "m1", start=6 * S, offset=6 * S, length=3 * S, clip_id="b")
    p = ops.set_clip(p, "b", muted=True)
    p = ops.add_clip(p, "B", "m2", start=1 * S, offset=1 * S, length=2 * S, clip_id="c")
    p = ops.add_clip(p, "B", "m2", start=7 * S, offset=0, length=2 * S, clip_id="d")
    return ops.add_marker(p, "mk", "m", 8 * S)


def span(p: Project, clip_id: str):
    c = p.clip(clip_id)
    return c.start, c.end, c.offset


def test_both_ops_are_in_the_edit_table():
    assert "roll_trim" in ops.OPS
    assert "ripple_trim" in ops.OPS


def test_dispatch_runs_them_by_name():
    p = ops.apply(project(), "roll_trim", {"clip_id": "a", "edge": "end", "frame": 7 * S})
    assert span(p, "a")[1] == 7 * S
    args = {"clip_id": "a", "edge": "end", "frame": 5 * S}
    p = ops.apply(project(), "ripple_trim", args)
    assert span(p, "a")[1] == 5 * S


def test_roll_end_moves_the_cut_point_between_touching_clips():
    p = ops.roll_trim(project(), "a", "end", 7 * S)
    assert span(p, "a") == (2 * S, 7 * S, 2 * S)
    assert span(p, "b") == (7 * S, 9 * S, 7 * S)  # start and source offset moved together


def test_roll_end_back_grows_the_neighbour():
    p = ops.roll_trim(project(), "a", "end", 5 * S)
    assert span(p, "a") == (2 * S, 5 * S, 2 * S)
    assert span(p, "b") == (5 * S, 9 * S, 5 * S)


def test_roll_start_moves_the_cut_point_to_the_left_neighbour():
    p = ops.roll_trim(project(), "b", "start", 5 * S)
    assert span(p, "a") == (2 * S, 5 * S, 2 * S)
    assert span(p, "b") == (5 * S, 9 * S, 5 * S)


def test_roll_changes_nothing_else():
    before = project()
    p = ops.roll_trim(before, "a", "end", 7 * S)
    assert p.track("B") == before.track("B")
    assert p.markers == before.markers


def test_roll_into_a_gap_is_a_plain_trim():
    p = ops.roll_trim(project(), "b", "end", 9 * S - S // 2)
    assert span(p, "b") == (6 * S, 9 * S - S // 2, 6 * S)
    p = ops.roll_trim(project(), "c", "end", 5 * S)
    assert span(p, "c") == (1 * S, 5 * S, 1 * S)
    assert span(p, "d") == (7 * S, 9 * S, 0)


def test_roll_clamps_so_the_neighbour_keeps_one_frame():
    p = ops.roll_trim(project(), "a", "end", 20 * S, overwrite=False)
    assert span(p, "a")[1] == 9 * S - 1
    assert p.clip("b").length == 1


def test_roll_clamps_so_the_dragged_clip_keeps_one_frame():
    p = ops.roll_trim(project(), "a", "end", 0)
    assert p.clip("a").length == 1
    assert p.clip("b").start == 2 * S + 1


def test_roll_clamps_to_the_start_of_the_media():
    # d has source offset 0 at 7 s: its start cannot go before 7 s.
    p = ops.roll_trim(project(), "d", "start", 3 * S)
    assert span(p, "d") == (7 * S, 9 * S, 0)


def test_roll_clamps_to_the_end_of_the_media():
    p = ops.roll_trim(project(), "b", "end", 30 * S)
    assert p.clip("b").end == 10 * S


def test_roll_neighbour_cannot_grow_past_its_source():
    p = ops.add_clip(project(), "B", "m1", start=10 * S, offset=0, length=S, clip_id="e")
    p = ops.add_clip(p, "B", "m1", start=11 * S, offset=4 * S, length=2 * S, clip_id="f")
    # f's source starts 4 s in, so its start can move back 4 s at most (to 7 s), but e
    # (10-11 s) is the dragged clip here: e's end cannot go before its own start + 1.
    p = ops.roll_trim(p, "e", "end", 10 * S + 1, overwrite=False)
    assert span(p, "f") == (10 * S + 1, 13 * S, 4 * S - (S - 1))
    # Dragging f's start back past 7 s hits f's own source start, not e.
    p = ops.roll_trim(p, "f", "start", 0, overwrite=False)
    assert p.clip("f").start == 10 * S + 1  # e keeps one frame
    assert p.clip("e").length == 1


def test_ripple_end_shorter_pulls_everything_after_it_on_all_tracks():
    p = ops.ripple_trim(project(), "a", "end", 5 * S)
    assert span(p, "a") == (2 * S, 5 * S, 2 * S)
    assert span(p, "b") == (5 * S, 8 * S, 6 * S)
    assert span(p, "c") == (1 * S, 3 * S, 1 * S)
    assert span(p, "d") == (6 * S, 8 * S, 0)
    assert p.markers[0].start == 7 * S


def test_ripple_end_longer_pushes_everything_after_it_on_all_tracks():
    p = ops.ripple_trim(project(), "a", "end", 8 * S - S // 2)
    assert span(p, "a") == (2 * S, 8 * S - S // 2, 2 * S)
    assert span(p, "b") == (8 * S - S // 2, 11 * S - S // 2, 6 * S)
    assert span(p, "d") == (9 * S - S // 2, 11 * S - S // 2, 0)
    assert span(p, "c") == (1 * S, 3 * S, 1 * S)
    assert p.markers[0].start == 10 * S - S // 2


def test_ripple_start_keeps_the_clip_in_place_and_shifts_what_follows():
    p = ops.ripple_trim(project(), "a", "start", 3 * S)
    assert span(p, "a") == (2 * S, 5 * S, 3 * S)
    assert span(p, "b") == (5 * S, 8 * S, 6 * S)
    assert span(p, "d") == (6 * S, 8 * S, 0)


def test_ripple_start_longer_reveals_earlier_source():
    p = ops.ripple_trim(project(), "a", "start", 1 * S)
    assert span(p, "a") == (2 * S, 7 * S, 1 * S)
    assert span(p, "b") == (7 * S, 10 * S, 6 * S)


def test_ripple_clamps_to_the_media_and_to_one_frame():
    p = ops.ripple_trim(project(), "a", "end", 99 * S)
    assert p.clip("a").end == 10 * S
    p = ops.ripple_trim(project(), "a", "end", 0)
    assert p.clip("a").length == 1
    p = ops.ripple_trim(project(), "a", "start", -5 * S)
    assert p.clip("a").offset == 0
    p = ops.ripple_trim(project(), "a", "start", 99 * S)
    assert p.clip("a").length == 1


def test_ripple_leaves_earlier_things_alone():
    before = project()
    p = ops.ripple_trim(before, "d", "end", 8 * S)
    assert p.clip("c") == before.clip("c")
    assert p.clip("a") == before.clip("a")
    # A clip that plays through the lost stretch loses it too (as X does).
    assert span(p, "b") == (6 * S, 8 * S, 6 * S)


@pytest.mark.parametrize("op", ["roll_trim", "ripple_trim"])
def test_bad_edge_and_missing_clip_are_refused(op):
    with pytest.raises(ops.EditError):
        ops.apply(project(), op, {"clip_id": "a", "edge": "middle", "frame": 1})
    with pytest.raises(ops.EditError):
        ops.apply(project(), op, {"clip_id": "zz", "edge": "end", "frame": 1})


# -- an edge drag overwrites its neighbours by default (WP83, owner 2026-10-19) ----------


def three() -> Project:
    """One track: clips 1 (2-4 s), 2 (4-5 s, muted) and 3 (5-9 s), source = timeline."""
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=10 * S))
    p = ops.add_track(p, track_id="T", name="T")
    for cid, a, b in (("c1", 2, 4), ("c2", 4, 5), ("c3", 5, 9)):
        p = ops.add_clip(p, "T", "m", start=a * S, offset=a * S, length=(b - a) * S,
                         clip_id=cid)
    p = ops.set_clip(p, "c1", muted=True)
    return ops.set_clip(p, "c2", muted=True)


def ids_on(p: Project) -> list[str]:
    return [c.id for c in p.tracks[0].clips]


def test_start_edge_dragged_left_covers_several_clips():
    p = ops.roll_trim(three(), "c3", "start", 3 * S)
    assert ids_on(p) == ["c1", "c3"]  # c2 covered whole: gone
    assert span(p, "c1") == (2 * S, 3 * S, 2 * S)  # c1 trimmed, not a stop
    assert span(p, "c3") == (3 * S, 9 * S, 3 * S)


def test_start_edge_removes_every_clip_it_covers_whole():
    p = ops.roll_trim(three(), "c3", "start", 2 * S)
    assert ids_on(p) == ["c3"]


def test_start_edge_is_bounded_by_its_own_source_only():
    p = ops.add_clip(three(), "T", "m", start=0, offset=0, length=S, clip_id="c0")
    p = ops.roll_trim(p, "c3", "start", -4 * S)  # c3's source starts at 0 s
    assert ids_on(p) == ["c3"]
    assert span(p, "c3") == (0, 9 * S, 0)


def test_start_edge_stops_at_the_source_start():
    q = ops.trim_clip(three(), "c3", start=6 * S)  # c3 6-9 s, source before it hidden
    p = ops.roll_trim(q, "c3", "start", 0)
    assert span(p, "c3") == (0, 9 * S, 0)
    assert ids_on(p) == ["c3"]


def test_start_edge_stops_where_the_source_runs_out():
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=10 * S))
    p = ops.add_track(p, track_id="T", name="T")
    p = ops.add_clip(p, "T", "m", start=1 * S, offset=0, length=S, clip_id="x")
    p = ops.add_clip(p, "T", "m", start=3 * S, offset=2 * S, length=S, clip_id="y")
    # y's source begins 2 s in, so its start edge cannot go before 1 s.
    p = ops.roll_trim(p, "y", "start", 0)
    assert span(p, "y") == (1 * S, 4 * S, 0)
    assert ids_on(p) == ["y"]  # x lay wholly under it


def test_end_edge_dragged_right_covers_several_clips():
    q = ops.trim_clip(three(), "c1", end=3 * S)  # c1 2-3 s, a gap, c2, c3
    q = ops.add_clip(q, "T", "m", start=0, offset=0, length=S, clip_id="c0")
    frame = 45 * S // 10
    p = ops.roll_trim(q, "c0", "end", frame)  # over c1 (whole) and c2 (front)
    assert ids_on(p) == ["c0", "c2", "c3"]
    assert span(p, "c0") == (0, frame, 0)
    assert span(p, "c2")[0] == frame


def test_end_edge_is_bounded_by_its_own_source_end():
    q = ops.trim_clip(three(), "c1", end=3 * S)
    p = ops.roll_trim(q, "c1", "end", 99 * S)
    assert span(p, "c1")[1] == 10 * S
    assert ids_on(p) == ["c1"]


def test_without_overwrite_the_edge_stops_at_the_neighbour():
    p = ops.roll_trim(three(), "c3", "start", 3 * S, overwrite=False)
    assert span(p, "c1") == (2 * S, 4 * S, 2 * S)
    assert span(p, "c3")[0] == 4 * S + 1


def test_without_overwrite_a_gap_extend_stops_at_the_next_clip():
    q = ops.trim_clip(three(), "c1", end=3 * S)
    p = ops.roll_trim(q, "c1", "end", 45 * S // 10, overwrite=False)
    assert span(p, "c1")[1] == 4 * S
    assert ids_on(p) == ["c1", "c2", "c3"]


def test_shrinking_an_edge_is_unchanged():
    p = ops.roll_trim(three(), "c3", "start", 7 * S)
    assert span(p, "c2") == (4 * S, 7 * S, 4 * S)  # the neighbour grows
    assert span(p, "c3") == (7 * S, 9 * S, 7 * S)


def test_overwrite_is_available_through_dispatch():
    args = {"clip_id": "c3", "edge": "start", "frame": 3 * S, "overwrite": False}
    p = ops.apply(three(), "roll_trim", args)
    assert span(p, "c1") == (2 * S, 4 * S, 2 * S)


def test_one_undo_restores_everything(tmp_path):
    import numpy as np  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415

    from kuulas.session import Session  # noqa: PLC0415

    wav = tmp_path / "a.wav"
    sf.write(wav, np.zeros(10 * RATE, dtype=np.float32), RATE, subtype="PCM_16")
    s = Session(tmp_path / "One.kuulas")
    try:
        s.import_media([str(wav)])
        first = s.state.tracks[0].clips[0].id
        s.edit("split_clip", {"clip_id": first, "at": 4 * S})
        second = s.state.tracks[0].clips[1].id
        s.edit("split_clip", {"clip_id": second, "at": 5 * S})
        third = s.state.tracks[0].clips[2].id
        before = s.history.state
        s.edit("roll_trim", {"clip_id": third, "edge": "start", "frame": 3 * S})
        assert len(s.state.tracks[0].clips) == 2  # the middle clip is gone
        s.undo()
        assert s.history.state == before
    finally:
        s.close()
