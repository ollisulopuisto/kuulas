"""Putting a removed stretch back: the plan, and the one pure step that applies it (T64).

Same two-speaker example as test_put_back_locate: recording 2-3, 4-5 and 6-7 s were
ripple-cut on every track, so 7 s are left on the timeline and the seam of the 6-7 s
cut is at 4 s.
"""

import pytest

from kuulas import ops, put_back
from kuulas.clock import FLICKS
from kuulas.model import Clip, Media, Project, SyncGroup, Track
from kuulas.ops import EditError

RATE = 48_000
S = RATE


def fr(seconds):
    return round(seconds * S)


def fl(seconds):
    return round(seconds * FLICKS)


def clip(cid, media, start, offset, length, **kw):
    return Clip(cid, media, fr(start), fr(offset), fr(length), **kw)


def track(tid, clips, kind="speech"):
    return Track(tid, tid, kind=kind, clips=tuple(clips))


def rippled(media, tid):
    return track(tid, [clip(f"{tid}0", media, 0, 0, 2), clip(f"{tid}1", media, 2, 3, 1),
                       clip(f"{tid}2", media, 3, 5, 1), clip(f"{tid}3", media, 4, 7, 3)])


def project(tracks, *, b_frames=10, grouped=True, media=("a", "b")):
    items = tuple(Media(m, f"{m}.wav", 1, fr(b_frames if m == "b" else 10), sha256=m * 64)
                  for m in media)
    groups = ()
    if grouped:
        speakers = [m for m in media if m != "mus"]  # a bed is on no recording clock
        groups = (SyncGroup(id="g", main="a", members=tuple((m, 0) for m in speakers)),)
    return Project(rate=RATE, media=items, tracks=tuple(tracks), sync_groups=groups)


def two_speakers_and_music(**kw):
    music = track("tm", [Clip("m0", "mus", 0, 0, fr(7))], kind="music")
    return project([rippled("a", "ta"), rippled("b", "tb"), music],
                   media=("a", "b", "mus"), **kw)


def make_plan(p, start=6.0, end=7.0, **kw):
    return put_back.plan(p, "a", fl(start), fl(end), **kw)


def clips_of(p, tid):
    return sorted(p.track(tid).clips, key=lambda c: c.start)


def test_a_seam_put_back_is_a_ripple_insert_on_every_track():
    p = two_speakers_and_music()
    plan = make_plan(p)
    assert (plan.site.kind, plan.at, plan.mode) == (put_back.SEAM, fr(4), "insert")
    assert plan.shift == fr(1)
    new = put_back.apply(p, plan)
    for tid, media in (("ta", "a"), ("tb", "b")):
        restored = [c for c in new.track(tid).clips if c.offset == fr(6)]
        assert [(c.media, c.start, c.length) for c in restored] == [(media, fr(4), fr(1))]
        # What came after moved one second later: 7 s of clips + 1 s restored.
        assert max(c.end for c in new.track(tid).clips) == fr(8)


def test_the_speakers_stay_in_sync_after_a_put_back():
    p = two_speakers_and_music()
    new = put_back.apply(p, make_plan(p))
    on_clock = {
        tid: sorted((ops._recorded(new, c), c.start) for c in new.track(tid).clips)
        for tid in ("ta", "tb")}
    assert on_clock["ta"] == on_clock["tb"]


def test_other_tracks_open_a_gap_and_the_music_bed_is_split():
    p = two_speakers_and_music()
    plan = make_plan(p)
    assert dict(plan.outcomes) == {"ta": "restored", "tb": "restored", "tm": "split"}
    new = put_back.apply(p, plan)
    assert [(c.start, c.end) for c in clips_of(new, "tm")] == [(0, fr(4)), (fr(5), fr(8))]


def test_a_put_back_adds_clips_and_touches_no_recording():
    p = two_speakers_and_music()
    new = put_back.apply(p, make_plan(p))
    assert new.media == p.media
    count = sum(len(t.clips) for t in p.tracks)
    # Two restored clips (Anna, Ville) and one more piece where the music bed is split.
    assert sum(len(t.clips) for t in new.tracks) == count + 3


def test_scope_limits_which_tracks_open_a_gap():
    p = two_speakers_and_music()
    plan = make_plan(p, scope=["ta", "tb"])
    new = put_back.apply(p, plan)
    assert clips_of(new, "tm") == clips_of(p, "tm")


def test_a_partner_recording_that_does_not_reach_the_stretch_gets_silence():
    p = two_speakers_and_music(b_frames=6.5)
    plan = make_plan(p)
    assert dict(plan.outcomes)["tb"] == "silence"
    new = put_back.apply(p, plan)
    assert all(c.offset != fr(6) for c in new.track("tb").clips)
    assert max(c.end for c in new.track("tb").clips) == fr(8)  # still rippled, in sync


def test_a_gap_is_filled_in_place_and_nothing_moves():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 3, 3, 7)])
    p = project([ta], grouped=False, media=("a",))
    plan = make_plan(p, 2.0, 3.0)
    assert (plan.site.kind, plan.mode, plan.shift) == (put_back.HOLE, "place", 0)
    new = put_back.apply(p, plan)
    assert [(c.start, c.offset, c.length) for c in clips_of(new, "ta")] == [
        (0, 0, fr(2)), (fr(2), fr(2), fr(1)), (fr(3), fr(3), fr(7))]


def test_a_stretch_a_partner_still_plays_goes_back_on_this_track_only():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 3, 3, 7)])
    tb = track("tb", [clip("b0", "b", 0, 0, 10)])
    p = project([ta, tb])
    plan = make_plan(p, 2.0, 3.0)
    assert plan.site.kind == put_back.FILL
    assert dict(plan.outcomes) == {"ta": "restored", "tb": "still_in_edit"}
    new = put_back.apply(p, plan)
    assert new.track("tb") == p.track("tb")
    assert any(c.start == fr(2) and c.length == fr(1) for c in new.track("ta").clips)


def test_an_ambiguous_cut_is_blocked_until_a_place_is_given():
    tb = track("tb", [clip("b0", "b", 0, 0, 2), clip("b1", "b", 3, 3, 1),
                      clip("b2", "b", 4, 5, 1), clip("b3", "b", 5, 7, 3)])
    p = project([rippled("a", "ta"), tb])
    plan = make_plan(p)
    assert plan.blocked == "ambiguous"
    assert plan.site.candidates == (fr(4), fr(5))
    with pytest.raises(EditError):
        put_back.apply(p, plan)


def test_the_playhead_is_the_fallback_for_an_ambiguous_cut():
    tb = track("tb", [clip("b0", "b", 0, 0, 2), clip("b1", "b", 3, 3, 1),
                      clip("b2", "b", 4, 5, 1), clip("b3", "b", 5, 7, 3)])
    p = project([rippled("a", "ta"), tb])
    plan = make_plan(p, at=fr(4.5))
    assert plan.blocked == ""
    assert (plan.at, plan.mode) == (fr(4.5), "insert")
    new = put_back.apply(p, plan)
    restored = [c for c in new.track("ta").clips if c.offset == fr(6)]
    assert [(c.start, c.length) for c in restored] == [(fr(4.5), fr(1))]


def test_a_recording_that_is_nowhere_cannot_go_back_without_a_track():
    p = project([track("tm", [])], media=("a",), grouped=False)
    assert make_plan(p).blocked == "none"
    assert make_plan(p, at=fr(1)).blocked == "no_track"


def test_the_plan_says_how_far_later_everything_moves():
    p = two_speakers_and_music()
    plan = make_plan(p, 6.2, 6.5)
    assert plan.shift == fr(0.3)
    assert plan.length == fr(0.3)
