from dataclasses import replace

import pytest

from kuulas import ops
from kuulas.model import Media, Project

RATE = 48000


def project_with_two_tracks():
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m1", name="anna.wav", channels=1, frames=10 * RATE))
    p = ops.add_media(p, Media(id="m2", name="ville.wav", channels=1, frames=10 * RATE))
    p = ops.add_track(p, track_id="t1", name="Anna")
    p = ops.add_track(p, track_id="t2", name="Ville")
    p = ops.add_clip(p, track_id="t1", clip_id="c1", media_id="m1", start=0)
    return ops.add_clip(p, track_id="t2", clip_id="c2", media_id="m2", start=0)


def test_ops_never_mutate_the_previous_state():
    before = project_with_two_tracks()
    after = ops.set_clip(before, "c1", gain_db=-6.0)
    assert before.clip("c1").gain_db == 0.0
    assert after.clip("c1").gain_db == -6.0


def test_add_clip_defaults_to_whole_media():
    p = project_with_two_tracks()
    assert p.clip("c1").length == 10 * RATE


def test_split_keeps_audio_in_place():
    p = ops.split_clip(project_with_two_tracks(), "c1", at=4 * RATE, new_id="c1b")
    left, right = p.track("t1").clips
    assert (left.start, left.offset, left.length) == (0, 0, 4 * RATE)
    assert (right.start, right.offset, right.length) == (4 * RATE, 4 * RATE, 6 * RATE)


def test_split_outside_clip_is_refused():
    with pytest.raises(ops.EditError):
        ops.split_clip(project_with_two_tracks(), "c1", at=11 * RATE, new_id="x")


def test_trim_start_moves_offset_with_it():
    p = ops.trim_clip(project_with_two_tracks(), "c1", start=2 * RATE)
    c = p.clip("c1")
    assert (c.start, c.offset, c.length) == (2 * RATE, 2 * RATE, 8 * RATE)


def test_trim_cannot_reach_past_the_media():
    p = ops.trim_clip(project_with_two_tracks(), "c1", start=2 * RATE)
    p = ops.trim_clip(p, "c1", start=-5 * RATE)
    c = p.clip("c1")
    assert (c.start, c.offset) == (0, 0)
    p = ops.trim_clip(p, "c1", end=20 * RATE)
    assert p.clip("c1").length == 10 * RATE


def test_move_clip_to_another_track():
    p = ops.move_clip(project_with_two_tracks(), "c1", start=RATE, track_id="t2")
    assert [c.id for c in p.track("t1").clips] == []
    assert sorted(c.id for c in p.track("t2").clips) == ["c1", "c2"]
    assert p.clip("c1").start == RATE


def test_ripple_delete_cuts_every_track_and_closes_the_gap():
    p = ops.ripple_delete(project_with_two_tracks(), 2 * RATE, 3 * RATE)
    for track in p.tracks:
        a, b = track.clips
        assert (a.start, a.offset, a.length) == (0, 0, 2 * RATE)
        assert (b.start, b.offset, b.length) == (2 * RATE, 3 * RATE, 7 * RATE)


def test_ripple_join_of_non_adjacent_audio_gets_a_crossfade():
    p = ops.ripple_delete(project_with_two_tracks(), 2 * RATE, 3 * RATE)
    a, b = p.track("t1").clips
    xf = round(ops.CROSSFADE_SEC * RATE)
    assert (a.xfade_out, b.xfade_in) == (xf, xf)
    assert (a.xfade_in, b.xfade_out) == (0, 0)


def test_plain_split_of_adjacent_audio_has_no_crossfade():
    p = ops.split_clip(project_with_two_tracks(), "c1", at=4 * RATE, new_id="c1b")
    a, b = p.track("t1").clips
    assert (a.xfade_out, b.xfade_in, a.fade_out, b.fade_in) == (0, 0, 0, 0)


def test_a_cut_with_nothing_before_it_gets_no_crossfade():
    p = ops.ripple_delete(project_with_two_tracks(), 0, RATE)
    assert p.track("t1").clips[0].xfade_in == 0


def test_trimming_an_edge_drops_its_crossfade():
    p = ops.ripple_delete(project_with_two_tracks(), 2 * RATE, 3 * RATE)
    left = p.track("t1").clips[0]
    p = ops.trim_clip(p, left.id, end=RATE)
    assert p.clip(left.id).xfade_out == 0


def test_ripple_delete_shifts_track_automation_and_keeps_its_shape():
    p = project_with_two_tracks()
    # Ramp 0 dB at 1 s to -10 dB at 5 s: -2.5 dB/s.
    p = ops.set_track_automation(p, "t1", [(RATE, 0.0), (5 * RATE, -10.0)])
    p = ops.ripple_delete(p, 2 * RATE, 3 * RATE)
    points = p.track("t1").automation
    assert points[0] == (RATE, 0.0)
    # The cut joins 2 s (-2.5 dB) to what was 3 s (-5 dB) at 2 s.
    assert (2 * RATE, -2.5) in points
    assert (2 * RATE, -5.0) in points
    assert points[-1] == (4 * RATE, -10.0)


def test_ripple_delete_removes_clips_inside_the_range():
    p = ops.split_clip(project_with_two_tracks(), "c1", at=2 * RATE, new_id="c1b")
    p = ops.split_clip(p, "c1b", at=3 * RATE, new_id="c1c")
    p = ops.ripple_delete(p, 2 * RATE, 3 * RATE, track_ids=["t1"])
    assert [c.id for c in p.track("t1").clips] == ["c1", "c1c"]
    # Other tracks untouched when the cut names its tracks.
    assert p.track("t2").clips[0].length == 10 * RATE


def test_clip_envelope_lives_in_source_time_so_trims_keep_it():
    p = ops.set_clip_envelope(project_with_two_tracks(), "c1", [(5 * RATE, -6.0)])
    p = ops.trim_clip(p, "c1", start=3 * RATE)
    assert p.clip("c1").envelope == ((5 * RATE, -6.0),)


def test_bus_routing():
    p = ops.add_bus(project_with_two_tracks(), bus_id="b1", name="Voices")
    p = ops.set_track(p, "t1", bus="b1")
    assert p.track("t1").bus == "b1"
    with pytest.raises(ops.EditError):
        ops.set_track(p, "t1", bus="nope")


def test_deleting_a_bus_reroutes_its_tracks_to_master():
    p = ops.add_bus(project_with_two_tracks(), bus_id="b1", name="Voices")
    p = ops.set_track(p, "t1", bus="b1")
    p = ops.delete_bus(p, "b1")
    assert p.track("t1").bus is None


def test_project_round_trips_through_json():
    p = ops.set_clip_envelope(project_with_two_tracks(), "c1", [(5, -1.5)])
    p = ops.add_bus(p, bus_id="b1", name="Voices")
    assert Project.from_json(p.to_json()) == p


def test_apply_dispatches_by_name():
    p = ops.apply(project_with_two_tracks(), "set_clip", {"clip_id": "c1", "pan": -0.5})
    assert p.clip("c1").pan == -0.5
    with pytest.raises(ops.EditError):
        ops.apply(p, "__class__", {})


def test_clips_from_a_moment_onwards_on_every_track():
    p = ops.split_clip(project_with_two_tracks(), "c1", at=4 * RATE, new_id="c1b")
    # The clip under the playhead counts: it is "from this moment on".
    assert ops.clips_from(p, 5 * RATE) == ["c1b", "c2"]
    assert ops.clips_from(p, 5 * RATE, track_id="t1") == ["c1b"]
    assert ops.clips_until(p, 3 * RATE, track_id="t1") == ["c1"]


def test_shift_clips_moves_a_selection_as_one_edit():
    p = ops.split_clip(project_with_two_tracks(), "c1", at=4 * RATE, new_id="c1b")
    p = ops.shift_clips(p, ["c1b", "c2"], 2 * RATE)
    assert p.clip("c1b").start == 6 * RATE
    assert p.clip("c2").start == 2 * RATE
    assert p.clip("c1").start == 0


def test_shift_clips_stops_at_zero_without_changing_spacing():
    p = ops.shift_clips(project_with_two_tracks(), ["c1", "c2"], -5 * RATE)
    assert (p.clip("c1").start, p.clip("c2").start) == (0, 0)


def test_selection_wide_edits():
    p = ops.set_clips(project_with_two_tracks(), ["c1", "c2"], gain_db=-3.0)
    assert p.clip("c1").gain_db == p.clip("c2").gain_db == -3.0
    p = ops.delete_clips(p, ["c1", "c2"])
    assert all(not t.clips for t in p.tracks)


def test_set_clips_empty_returns_unchanged():
    p = project_with_two_tracks()
    assert ops.set_clips(p, [], gain_db=-3.0) == p


def test_set_clips_unknown_clip_raises_edit_error():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.set_clips(p, ["c1", "nonexistent"], gain_db=-3.0)
    assert exc_info.value.key == "error.edit.no_clip"


def test_set_clips_rejects_a_missing_id_from_a_one_shot_iterator():
    p = project_with_two_tracks()
    clip_ids = (clip_id for clip_id in ("c1", "missing"))

    with pytest.raises(ops.EditError) as exc_info:
        ops.set_clips(p, clip_ids, muted=True)

    assert exc_info.value.key == "error.edit.no_clip"


def test_set_clips_changes_only_the_first_track_with_a_duplicate_id():
    p = project_with_two_tracks()
    p = ops.add_clip(p, track_id="t2", media_id="m2", clip_id="c1")

    q = ops.set_clips(p, ["c1"], muted=True)

    assert p.track("t1").clips[0].muted is False
    assert q.track("t1").clips[0].muted is True
    assert next(c for c in q.track("t2").clips if c.id == "c1").muted is False


def test_set_clips_sorts_changed_track_clips():
    p = project_with_two_tracks()
    p = ops.add_clip(p, track_id="t1", media_id="m1", clip_id="late",
                     start=5 * RATE)
    p = replace(p, tracks=(replace(p.track("t1"),
                                  clips=tuple(reversed(p.track("t1").clips))),
                           p.track("t2")))

    q = ops.set_clips(p, ["late"], name="renamed")

    assert [(clip.id, clip.start) for clip in q.track("t1").clips] == [
        ("c1", 0), ("late", 5 * RATE)
    ]


def test_set_clips_invalid_field_raises_edit_error():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.set_clips(p, ["c1"], invalid_field=123)
    assert exc_info.value.key == "error.edit.clip_no_fields"


def test_set_clips_clamps_and_normalizes_fields():
    p = project_with_two_tracks()
    p2 = ops.set_clips(
        p,
        ["c1", "c2"],
        pan=-2.5,
        fade_in=999999999,
        fade_out=-50,
        name="  Test Clip  ",
    )
    for cid in ("c1", "c2"):
        c = p2.clip(cid)
        assert c.pan == -1.0
        assert c.fade_in == c.length
        assert c.fade_out == 0
        assert c.name == "Test Clip"


def test_delete_clips_empty_or_subset():
    p = project_with_two_tracks()
    assert ops.delete_clips(p, []) == p
    p_subset = ops.delete_clips(p, ["c1"])
    assert [c.id for c in p_subset.track("t1").clips] == []
    assert [c.id for c in p_subset.track("t2").clips] == ["c2"]


def test_delete_clips_unknown_clip_raises_edit_error():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.delete_clips(p, ["c1", "nonexistent"])
    assert exc_info.value.key == "error.edit.no_clip"
    assert exc_info.value.params == {"clip_id": "nonexistent"}


def test_add_bus_with_track_ids_assigns_them_in_the_same_edit():
    p = ops.add_bus(project_with_two_tracks(), bus_id="b1", name="Voices",
                    track_ids=["t1", "t2"])
    assert [b.id for b in p.buses] == ["b1"]
    assert p.track("t1").bus == "b1"
    assert p.track("t2").bus == "b1"


def test_add_bus_accepts_one_shot_track_ids():
    track_ids = (track_id for track_id in ("t1", "t2"))
    p = ops.add_bus(project_with_two_tracks(), bus_id="b1", name="Voices",
                    track_ids=track_ids)
    assert p.track("t1").bus == "b1"
    assert p.track("t2").bus == "b1"


def test_add_bus_rejects_unknown_track_in_one_shot_track_ids():
    track_ids = (track_id for track_id in ("t1", "nope"))
    with pytest.raises(ops.EditError) as exc_info:
        ops.add_bus(project_with_two_tracks(), track_ids=track_ids)
    assert exc_info.value.key == "error.edit.no_track"
    assert exc_info.value.params == {"track_id": "nope"}


def test_add_bus_rejects_duplicate_id():
    p = ops.add_bus(project_with_two_tracks(), bus_id="b1", name="Voices")
    with pytest.raises(ops.EditError) as exc_info:
        ops.add_bus(p, bus_id="b1", name="Voices duplicate")
    assert exc_info.value.key == "error.edit.bus_exists"
    assert exc_info.value.params == {"bus_id": "b1"}


def test_add_bus_with_an_unknown_track_changes_nothing():
    before = project_with_two_tracks()
    with pytest.raises(ops.EditError):
        ops.add_bus(before, track_ids=["t1", "nope"])
    assert before.buses == ()


def test_add_track_rejects_duplicate_id():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.add_track(p, track_id="t1", name="Duplicate Track")
    assert exc_info.value.key == "error.edit.track_exists"
    assert exc_info.value.params == {"track_id": "t1"}


def test_adjust_clip_gain_batch_updates_and_clamps():
    p = project_with_two_tracks()
    # Add a third clip on t1 that is NOT selected
    p = ops.add_clip(p, track_id="t1", clip_id="c3", media_id="m1", start=12 * RATE)
    p = ops.adjust_clip_gain(p, ["c1", "c2"], 3.5)
    assert p.clip("c1").gain_db == 3.5
    assert p.clip("c2").gain_db == 3.5
    assert p.clip("c3").gain_db == 0.0

    # Test clamping to CLIP_GAIN_RANGE (-60.0, 12.0)
    p_high = ops.adjust_clip_gain(p, ["c1"], 100.0)
    assert p_high.clip("c1").gain_db == 12.0
    p_low = ops.adjust_clip_gain(p, ["c1"], -100.0)
    assert p_low.clip("c1").gain_db == -60.0


def test_adjust_clip_gain_empty_raises_error():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.adjust_clip_gain(p, [], 1.0)
    assert exc_info.value.key == "error.edit.no_selection"


def test_adjust_clip_gain_unknown_clip_raises_error():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.adjust_clip_gain(p, ["c1", "nonexistent"], 1.0)
    assert exc_info.value.key == "error.edit.no_clip"
    assert exc_info.value.params == {"clip_id": "nonexistent"}


def test_adjust_clip_gain_accepts_one_shot_iterator():
    p = project_with_two_tracks()
    one_shot = (cid for cid in ["c1", "c2"])
    p_res = ops.adjust_clip_gain(p, one_shot, -2.5)
    assert p_res.clip("c1").gain_db == -2.5
    assert p_res.clip("c2").gain_db == -2.5


def test_trim_clips_batch_updates_start_and_end():
    p = project_with_two_tracks()
    p = ops.add_clip(p, track_id="t1", clip_id="c3", media_id="m1", start=12 * RATE)
    p_trimmed = ops.trim_clips(p, ["c1", "c2"], start=2 * RATE, end=8 * RATE)
    c1 = p_trimmed.clip("c1")
    c2 = p_trimmed.clip("c2")
    c3 = p_trimmed.clip("c3")
    assert c1.start == 2 * RATE
    assert c1.end == 8 * RATE
    assert c1.offset == 2 * RATE
    assert c1.length == 6 * RATE

    assert c2.start == 2 * RATE
    assert c2.end == 8 * RATE
    assert c2.offset == 2 * RATE
    assert c2.length == 6 * RATE

    assert c3.start == 12 * RATE


def test_trim_clips_empty_selection_returns_same_project():
    p = project_with_two_tracks()
    p_same = ops.trim_clips(p, [])
    assert p_same == p


def test_trim_clips_unknown_clip_raises_error():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.trim_clips(p, ["c1", "nonexistent"], start=RATE)
    assert exc_info.value.key == "error.edit.no_clip"
    assert exc_info.value.params == {"clip_id": "nonexistent"}


def test_trim_clips_empty_trim_refuses_all():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.trim_clips(p, ["c1", "c2"], start=11 * RATE)
    assert exc_info.value.key == "error.edit.trim_empty"
    assert p.clip("c1").start == 0
    assert p.clip("c2").start == 0


def test_trim_clips_accepts_one_shot_iterator():
    p = project_with_two_tracks()
    one_shot = (cid for cid in ["c1", "c2"])
    p_res = ops.trim_clips(p, one_shot, start=RATE)
    assert p_res.clip("c1").start == RATE
    assert p_res.clip("c2").start == RATE


def project_with_duplicate_clip_id_on_two_tracks():
    # Imported or merged projects can carry the same clip id on separate tracks.
    p = project_with_two_tracks()
    return ops.add_clip(p, track_id="t2", clip_id="c1", media_id="m2", start=0)


def test_trim_clips_trims_a_duplicated_id_on_the_first_track_only():
    p = project_with_duplicate_clip_id_on_two_tracks()
    out = ops.trim_clips(p, ["c1"], start=2 * RATE)
    first = next(t for t in out.tracks if t.id == "t1")
    second = next(t for t in out.tracks if t.id == "t2")
    assert [c.start for c in first.clips if c.id == "c1"] == [2 * RATE]
    assert [c.start for c in second.clips if c.id == "c1"] == [0]


def test_trim_clips_reports_a_missing_id_before_an_invalid_trim():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.trim_clips(p, ["missing", "c1"], start=11 * RATE)
    assert exc_info.value.key == "error.edit.no_clip"
    assert exc_info.value.params == {"clip_id": "missing"}


def test_trim_clips_stops_at_the_first_error_in_caller_order():
    p = project_with_two_tracks()
    with pytest.raises(ops.EditError) as exc_info:
        ops.trim_clips(p, ["c1", "missing"], start=11 * RATE)
    assert exc_info.value.key == "error.edit.trim_empty"
