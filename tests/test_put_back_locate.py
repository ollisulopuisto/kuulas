"""Where removed material goes back: the seam, measured on the recording clock (T64).

The owner's example (docs/PLAN.md, Put back): two speakers on one clock, recording
seconds 2-3, 4-5 and 6-7 ripple-cut on every track. A hit at 6.2 s of Anna's recording
goes back at the seam on the timeline where 6-7 was cut, which is 4 s.
"""

from kuulas import put_back
from kuulas.clock import FLICKS
from kuulas.model import Clip, Media, Project, SyncGroup, Track

RATE = 48_000
S = RATE


def fr(seconds):
    return round(seconds * S)


def fl(seconds):
    return round(seconds * FLICKS)


def clip(cid, media, start, offset, length, **kw):
    return Clip(cid, media, fr(start), fr(offset), fr(length), **kw)


def project(tracks, *, grouped=True, media=("a", "b")):
    items = tuple(Media(m, f"{m}.wav", 1, fr(10), sha256=m * 64) for m in media)
    groups = ()
    if grouped:
        groups = (SyncGroup(id="g", main=media[0], members=tuple((m, 0) for m in media)),)
    return Project(rate=RATE, media=items, tracks=tuple(tracks), sync_groups=groups)


def track(tid, clips, kind="speech"):
    return Track(tid, tid, kind=kind, clips=tuple(clips))


def rippled(media, tid):
    """Recording 2-3, 4-5 and 6-7 s cut out and closed up: 7 s left on the timeline."""
    return track(tid, [clip(f"{tid}0", media, 0, 0, 2), clip(f"{tid}1", media, 2, 3, 1),
                       clip(f"{tid}2", media, 3, 5, 1), clip(f"{tid}3", media, 4, 7, 3)])


def site(p, media, start, end):
    return put_back.locate(p, media, fl(start), fl(end))


def test_a_cut_on_every_track_goes_back_at_the_seam():
    p = project([rippled("a", "ta"), rippled("b", "tb")])
    found = site(p, "a", 6.0, 7.0)
    assert found.kind == put_back.SEAM
    assert found.frame == fr(4)


def test_the_hit_inside_the_cut_stretch_still_finds_the_same_seam():
    p = project([rippled("a", "ta"), rippled("b", "tb")])
    assert site(p, "a", 6.2, 6.5).frame == fr(4)


def test_an_earlier_cut_has_its_own_seam():
    p = project([rippled("a", "ta"), rippled("b", "tb")])
    assert site(p, "a", 2.0, 3.0).frame == fr(2)


def test_a_gap_left_on_one_track_is_a_hole_filled_in_place():
    # Recording 2-3 s was deleted without closing the gap (the next piece stayed at 3 s).
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 3, 3, 7)])
    p = project([ta], grouped=False, media=("a",))
    found = site(p, "a", 2.2, 2.8)
    assert found.kind == put_back.HOLE
    assert found.frame == fr(2.2)
    assert found.track == "ta"


def test_material_a_partner_still_plays_is_filled_in_on_this_track():
    # Anna's 2-3 s is gone (gap), Ville still plays it: put it back where Ville has it.
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 3, 3, 7)])
    tb = track("tb", [clip("b0", "b", 0, 0, 10)])
    p = project([ta, tb])
    found = site(p, "a", 2.0, 3.0)
    assert found.kind == put_back.FILL
    assert found.frame == fr(2)
    assert found.track == "ta"


def test_a_fill_that_runs_into_another_clip_is_ambiguous():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a9", "a", 2.5, 8, 1),
                      clip("a1", "a", 3, 3, 7)])
    tb = track("tb", [clip("b0", "b", 0, 0, 10)])
    p = project([ta, tb])
    assert site(p, "a", 2.0, 3.0).kind == put_back.AMBIGUOUS


def test_material_before_the_cut_only_goes_back_at_its_edge():
    ta = track("ta", [clip("a0", "a", 0, 0, 2)])
    tb = track("tb", [clip("b0", "b", 0, 0, 2)])
    p = project([ta, tb])
    found = site(p, "a", 5.0, 6.0)
    assert found.kind == put_back.EDGE
    assert found.frame == fr(2)


def test_material_after_the_cut_only_goes_back_at_its_start():
    ta = track("ta", [clip("a0", "a", 0, 7, 3)])
    tb = track("tb", [clip("b0", "b", 0, 7, 3)])
    p = project([ta, tb])
    found = site(p, "a", 2.0, 3.0)
    assert found.kind == put_back.EDGE
    assert found.frame == 0


def test_seams_that_disagree_between_tracks_are_not_guessed():
    # Ville's pieces were closed up differently: his seam is at 5 s, Anna's at 4 s.
    tb = track("tb", [clip("b0", "b", 0, 0, 2), clip("b1", "b", 3, 3, 1),
                      clip("b2", "b", 4, 5, 1), clip("b3", "b", 5, 7, 3)])
    p = project([rippled("a", "ta"), tb])
    found = site(p, "a", 6.0, 7.0)
    assert found.kind == put_back.AMBIGUOUS
    assert found.candidates == (fr(4), fr(5))


def test_neighbours_on_different_tracks_are_ambiguous():
    ta = track("ta", [clip("a0", "a", 0, 0, 2)])
    tb = track("tb", [clip("b0", "b", 0, 7, 3)])
    p = project([ta, tb])
    assert site(p, "a", 4.0, 5.0).kind == put_back.AMBIGUOUS


def test_a_recording_nowhere_on_the_timeline_has_no_place():
    p = project([track("tm", [])])
    found = site(p, "a", 2.0, 3.0)
    assert found.kind == put_back.NONE
    assert found.frame is None


def test_music_and_other_recordings_are_not_part_of_the_seam():
    # A music clip across the cut does not count: it is not in the recording's group.
    music = Track("tm", "Music", kind="music", clips=(Clip("m0", "mus", 0, 0, fr(7)),))
    p = project([rippled("a", "ta"), rippled("b", "tb"), music], media=("a", "b", "mus"))
    p = Project(rate=RATE, media=p.media, tracks=p.tracks, sync_groups=(
        SyncGroup(id="g", main="a", members=(("a", 0), ("b", 0))),))
    assert site(p, "a", 6.0, 7.0).frame == fr(4)


def test_a_clip_free_from_sync_is_not_a_reference():
    free = track("tb", [clip("b0", "b", 0, 0, 2, free=True),
                        clip("b3", "b", 9, 7, 3, free=True)])
    p = project([rippled("a", "ta"), free])
    assert site(p, "a", 6.0, 7.0).frame == fr(4)


def test_an_offset_between_the_recordings_is_applied():
    # Ville's file started 1 s after Anna's: his frame 0 is the group's 1 s.
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 2, 3, 7)])
    tb = track("tb", [clip("b0", "b", 1, 0, 1), clip("b1", "b", 2, 2, 8)])
    p = project([ta, tb])
    p = Project(rate=RATE, media=p.media, tracks=p.tracks, sync_groups=(
        SyncGroup(id="g", main="a", members=(("a", 0), ("b", fl(1)))),))
    # Anna's 2-3 s is rec 2-3; Ville's pieces cut b's 1-2 s = rec 2-3 as well.
    assert site(p, "a", 2.0, 3.0).frame == fr(2)
