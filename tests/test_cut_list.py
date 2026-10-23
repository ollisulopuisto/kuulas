"""The cut list: where the audio edit jumps, per track, on the timeline and on the
recording clock (owner, 2026-10-23: hiding one speaker's cuts is the most useful thing a
video rough cut can learn from kuulas; see ROADMAP "Final Cut XML in and out").

Same two-speaker example as test_put_back_plan: recording 2-3, 4-5 and 6-7 s were
ripple-cut on every track, so the seams are at 2, 3 and 4 s on the timeline.
"""

import json

from kuulas import cut_list
from kuulas.clock import FLICKS
from kuulas.model import Clip, Media, Project, SyncGroup, Track

RATE = 48_000


def fr(seconds):
    return round(seconds * RATE)


def clip(cid, media, start, offset, length, **kw):
    return Clip(cid, media, fr(start), fr(offset), fr(length), **kw)


def track(tid, clips, kind="speech", speaker=""):
    return Track(tid, tid, kind=kind, speaker=speaker, clips=tuple(clips))


def rippled(media, tid, speaker=""):
    return track(tid, [clip(f"{tid}0", media, 0, 0, 2), clip(f"{tid}1", media, 2, 3, 1),
                       clip(f"{tid}2", media, 3, 5, 1), clip(f"{tid}3", media, 4, 7, 3)],
                 speaker=speaker)


def project(tracks, *, media=("a", "b"), grouped=True, origins=None):
    items = tuple(Media(m, f"{m}.wav", 1, fr(10), sha256=m * 64) for m in media)
    groups = ()
    if grouped:
        origins = origins or {}
        members = tuple((m, origins.get(m, 0)) for m in media if m != "mus")
        groups = (SyncGroup(id="g", main=media[0], members=members),)
    return Project(rate=RATE, media=items, tracks=tuple(tracks), sync_groups=groups)


def two_speakers(**kw):
    return project([rippled("a", "ta", "Anna"), rippled("b", "tb", "Ville")], **kw)


def cuts_of(result, tid):
    (found,) = [t for t in result["tracks"] if t["id"] == tid]
    return found["cuts"]


def test_every_ripple_cut_is_a_cut_on_each_speech_track():
    result = cut_list.cut_list(two_speakers())
    assert [(c["at"], c["removed"]) for c in cuts_of(result, "ta")] == [
        (fr(2), fr(1)), (fr(3), fr(1)), (fr(4), fr(1))]
    assert cuts_of(result, "ta") == cuts_of(result, "tb")


def test_a_cut_says_where_it_lands_on_the_recording_clock():
    cut = cuts_of(cut_list.cut_list(two_speakers()), "ta")[0]
    # The first piece ends at 2 s of the recording; the next one starts at 3 s.
    assert (cut["from"], cut["to"]) == (fr(2), fr(3))
    assert cut["clock"] == "g"


def test_the_recording_clock_includes_the_files_origin():
    # Ville's file started 1 s after Anna's: his frame 0 is the group's 1 s.
    p = two_speakers(origins={"b": round(1 * FLICKS)})
    cut = cuts_of(cut_list.cut_list(p), "tb")[0]
    assert (cut["from"], cut["to"]) == (fr(3), fr(4))
    assert cut["removed"] == fr(1)


def test_a_split_that_removes_nothing_is_not_a_cut():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 2, 2, 8)])
    p = project([ta], media=("a",))
    assert cuts_of(cut_list.cut_list(p), "ta") == []


def test_a_gap_is_not_a_cut():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 3, 3, 7)])
    p = project([ta], media=("a",))
    assert cuts_of(cut_list.cut_list(p), "ta") == []


def test_pieces_of_two_recordings_that_continue_one_clock_are_no_cut():
    # Anna's file ends at 2 s of the recording; Ville's covers the next stretch on the
    # same clock. Played one after the other, the recording clock does not jump.
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("b0", "b", 2, 2, 3)])
    p = project([ta])
    assert cuts_of(cut_list.cut_list(p), "ta") == []


def test_adjacent_pieces_of_unrelated_recordings_are_a_cut_with_no_clock():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("b0", "b", 2, 0, 3)])
    p = project([ta], grouped=False)
    [cut] = cuts_of(cut_list.cut_list(p), "ta")
    assert cut["at"] == fr(2)
    assert cut["clock"] is None
    assert cut["removed"] is None


def test_going_back_in_the_recording_is_a_negative_removal():
    ta = track("ta", [clip("a0", "a", 0, 5, 2), clip("a1", "a", 2, 1, 2)])
    p = project([ta], media=("a",))
    [cut] = cuts_of(cut_list.cut_list(p), "ta")
    assert (cut["from"], cut["to"], cut["removed"]) == (fr(7), fr(1), fr(-6))


def test_muting_does_not_make_or_hide_a_cut():
    ta = track("ta", [clip("a0", "a", 0, 0, 2, muted=True), clip("a1", "a", 2, 3, 1)])
    p = project([ta], media=("a",))
    assert len(cuts_of(cut_list.cut_list(p), "ta")) == 1


def test_music_tracks_are_left_out():
    music = track("tm", [clip("m0", "mus", 0, 0, 2), clip("m1", "mus", 2, 4, 2)],
                  kind="music")
    p = project([rippled("a", "ta"), music], media=("a", "mus"))
    result = cut_list.cut_list(p)
    assert [t["id"] for t in result["tracks"]] == ["ta"]


def test_seams_join_the_cuts_of_all_tracks_at_one_place():
    result = cut_list.cut_list(two_speakers())
    assert [(s["at"], s["removed"], s["tracks"]) for s in result["seams"]] == [
        (fr(2), fr(1), ["ta", "tb"]), (fr(3), fr(1), ["ta", "tb"]),
        (fr(4), fr(1), ["ta", "tb"])]


def test_a_seam_on_one_track_only_names_that_track():
    ta = track("ta", [clip("a0", "a", 0, 0, 2), clip("a1", "a", 2, 3, 1)])
    tb = track("tb", [clip("b0", "b", 0, 0, 10)])
    result = cut_list.cut_list(project([ta, tb]))
    [seam] = result["seams"]
    assert seam["tracks"] == ["ta"]


def test_the_list_names_the_speakers_and_the_recordings():
    result = cut_list.cut_list(two_speakers(origins={"b": round(1 * FLICKS)}))
    assert [(t["id"], t["speaker"]) for t in result["tracks"]] == [
        ("ta", "Anna"), ("tb", "Ville")]
    media = {m["id"]: m for m in result["media"]}
    assert media["a"]["sha256"] == "a" * 64
    assert media["a"]["name"] == "a.wav"
    assert media["b"]["clock"] == "g"
    assert media["b"]["origin_flicks"] == round(1 * FLICKS)


def test_the_header_says_what_the_numbers_are():
    result = cut_list.cut_list(two_speakers())
    assert result["format"] == "kuulas-cut-list"
    assert result["version"] == 1
    assert result["rate"] == RATE
    assert result["length"] == fr(7)


def test_the_list_is_plain_json():
    result = cut_list.cut_list(two_speakers())
    assert json.loads(json.dumps(result)) == result


def test_a_project_with_no_cuts_has_empty_lists():
    p = project([track("ta", [clip("a0", "a", 0, 0, 5)])], media=("a",))
    result = cut_list.cut_list(p)
    assert result["seams"] == []
    assert cuts_of(result, "ta") == []
