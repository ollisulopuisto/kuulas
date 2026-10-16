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
