"""Auto-sync: put a clip back in time with the rest of the room.

Two mics in one room hear each other, so the bleed on one is a delayed,
quieter copy of the other's speech; correlating the two finds the offset.
"""

from dataclasses import replace
from itertools import pairwise

import numpy as np
import pytest

from kuulas import ops
from kuulas.clock import frames_to_flicks
from kuulas.model import Media, Project

RATE = 8000


class MemoryStore:
    def __init__(self, arrays):
        self.arrays = arrays

    def read(self, media_id, first, count):
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


def talk(rng, n):
    """Irregular bursts: a rhythm with one best alignment, like speech."""
    env = np.zeros(n)
    t = 0
    while t < n:
        length = rng.integers(RATE // 10, RATE // 2)
        env[t:t + length] = rng.uniform(0.3, 1.0)
        t += length + rng.integers(RATE // 20, RATE // 2)
    return (env[:n] * rng.standard_normal(n)).astype(np.float32)


def room(offset_frames):
    rng = np.random.default_rng(5)
    n = 30 * RATE
    anna, ville = talk(rng, n), talk(rng, n)
    mic_a = anna + 0.1 * ville
    mic_v = ville + 0.1 * anna
    store = MemoryStore({"a": mic_a[None], "v": mic_v[None]})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="a", name="a.wav", channels=1, frames=n))
    p = ops.add_media(p, Media(id="v", name="v.wav", channels=1, frames=n))
    p = ops.add_track(p, track_id="A", name="Anna")
    p = ops.add_track(p, track_id="V", name="Ville")
    p = ops.add_clip(p, track_id="A", media_id="a", clip_id="ca")
    p = ops.add_clip(p, track_id="V", media_id="v", clip_id="cv", start=offset_frames)
    return p, store


def group(p, clip_id):
    """The sync group a clip's recording belongs to (membership is per media)."""
    g = p.sync_group(p.clip(clip_id).media)
    return None if g is None else g.id


def marked_room():
    """Anna is the main clip; Ville is marked in sync with her, then split."""
    p, store = room(offset_frames=0)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")
    p = ops.split_clip(p, "cv", at=10 * RATE, new_id="cv2")
    p = ops.split_clip(p, "cv2", at=20 * RATE, new_id="cv3")
    return p, store


def test_align_points_moves_candidate_and_marks_the_recordings_in_sync():
    p, _store = room(offset_frames=int(0.3 * RATE))

    q = ops.align_points(p, "ca", 12 * RATE, "cv", 9 * RATE)

    assert q.clip("cv").start == 3 * RATE
    assert group(q, "ca") == group(q, "cv")
    assert q.sync_group("a").main == "a"
    assert dict(q.sync_group("a").members)["v"] == frames_to_flicks(3 * RATE, RATE)
    assert p.clip("cv").start == int(0.3 * RATE)


def test_align_points_keeps_existing_anchor_group_partners():
    p, _store = room(offset_frames=0)
    p = ops.add_media(p, Media(id="c", name="c.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_track(p, track_id="C", name="C")
    p = ops.add_clip(p, track_id="C", media_id="c", clip_id="cc", start=RATE)
    p = ops.mark_in_sync(p, ["ca", "cc"], main="ca", group_id="g-a")

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert len(q.sync_groups) == 1
    assert group(q, "ca") == group(q, "cc") == group(q, "cv") == "g-a"
    assert q.sync_group("a").main == "a"
    assert dict(q.sync_group("a").members) == {
        "a": 0,
        "c": frames_to_flicks(RATE, RATE),
        "v": frames_to_flicks(2 * RATE, RATE),
    }


def test_align_points_merges_candidate_group_and_rebases_its_partners():
    p, _store = room(offset_frames=RATE // 2)
    for media_id, track_id, clip_id, start in (
        ("c", "C", "cc", RATE),
        ("d", "D", "cd", 4 * RATE),
    ):
        p = ops.add_media(p, Media(id=media_id, name=f"{media_id}.wav", channels=1,
                                   frames=30 * RATE))
        p = ops.add_track(p, track_id=track_id, name=track_id)
        p = ops.add_clip(p, track_id=track_id, media_id=media_id,
                         clip_id=clip_id, start=start)
    p = ops.mark_in_sync(p, ["ca", "cc"], main="ca", group_id="g-a")
    p = ops.mark_in_sync(p, ["cv", "cd"], main="cv", group_id="g-b")

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert len(q.sync_groups) == 1
    assert group(q, "ca") == group(q, "cc") == group(q, "cv") == group(q, "cd") == "g-a"
    assert q.sync_group("a").main == "a"
    assert dict(q.sync_group("a").members) == {
        "a": 0,
        "c": frames_to_flicks(RATE, RATE),
        "v": frames_to_flicks(2 * RATE, RATE),
        "d": frames_to_flicks(11 * RATE // 2, RATE),
    }


def test_align_points_reuses_candidate_group_when_anchor_has_no_group():
    p, _store = room(offset_frames=RATE // 2)
    p = ops.add_media(p, Media(id="d", name="d.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_track(p, track_id="D", name="D")
    p = ops.add_clip(p, track_id="D", media_id="d", clip_id="cd", start=4 * RATE)
    p = ops.mark_in_sync(p, ["cv", "cd"], main="cv", group_id="g-b")

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert len(q.sync_groups) == 1
    assert group(q, "ca") == group(q, "cv") == group(q, "cd") == "g-b"
    assert q.sync_group("v").main == "v"
    assert dict(q.sync_group("v").members) == {
        "a": frames_to_flicks(-2 * RATE, RATE),
        "v": 0,
        "d": frames_to_flicks(7 * RATE // 2, RATE),
    }


def test_align_points_overwrites_audio_on_the_anchor_track():
    p, _store = room(offset_frames=4 * RATE)
    p = ops.trim_clip(p, "ca", end=RATE)
    p = ops.move_clip(p, "cv", start=4 * RATE, track_id="A")
    p = ops.trim_clip(p, "cv", end=5 * RATE)

    q = ops.align_points(p, "ca", 3 * RATE // 4, "cv", RATE // 4)

    track = q.track("A")
    assert q.clip("cv").start == RATE // 2
    assert [(clip.id, clip.start, clip.end) for clip in track.clips] == [
        ("ca", 0, RATE // 2),
        ("cv", RATE // 2, 3 * RATE // 2),
    ]


def test_align_points_materializes_legacy_track_gate_before_moving_clip():
    p, _store = room(offset_frames=4 * RATE)
    p = ops.trim_clip(p, "cv", end=5 * RATE)
    p = ops.set_gate(p, "V", [(4 * RATE, 4 * RATE + RATE // 10)])

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert q.clip("cv").start == 2 * RATE
    assert q.track("V").gate == ()
    assert q.clip("cv").auto_silence == ((0, RATE // 10),)


def test_aligning_group_main_keeps_its_origin_when_changing_anchor_and_resyncing():
    p, _store = room(offset_frames=0)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="cv", group_id="g")

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert dict(q.sync_group("v").members)["v"] == 0
    q = ops.set_sync_anchor(q, "ca")
    q = ops.move_clip(q, "cv", start=9 * RATE)
    q = ops.resync(q, ["cv"])
    assert q.clip("cv").start == 2 * RATE


def test_align_points_preserves_resync_when_it_overwrites_the_anchor_clip():
    p, _store = room(offset_frames=0)
    p = ops.move_clip(p, "ca", start=2 * RATE)
    p = ops.trim_clip(p, "ca", end=3 * RATE)
    p = ops.add_media(p, Media(id="c", name="c.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_track(p, track_id="C", name="C")
    p = ops.add_clip(p, track_id="C", media_id="c", clip_id="cc", start=4 * RATE)
    p = ops.mark_in_sync(p, ["ca", "cc"], main="ca", group_id="g")
    p = ops.trim_clip(p, "cv", end=3 * RATE)
    p = ops.move_clip(p, "cv", start=0, track_id="A")

    q = ops.align_points(p, "ca", 0, "cv", 0)

    assert all(clip.id != "ca" for track in q.tracks for clip in track.clips)
    assert q.sync_group("c").main == "v"
    q = ops.move_clip(q, "cc", start=10 * RATE)
    q = ops.resync(q, ["cc"])
    assert q.clip("cc").start == 4 * RATE


def test_align_points_uses_candidate_when_anchor_piece_is_overwritten():
    p, _store = room(offset_frames=0)
    p = ops.add_media(p, Media(id="c", name="c.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_track(p, track_id="C", name="C")
    p = ops.add_clip(p, track_id="C", media_id="c", clip_id="cc", start=0)
    p = ops.mark_in_sync(p, ["ca", "cc"], main="cc", group_id="g")
    p = ops.delete_clip(p, "cc")
    p = ops.split_clip(p, "ca", at=3 * RATE, new_id="ca-later")
    p = ops.trim_clip(p, "ca", start=2 * RATE)
    p = ops.move_clip(p, "ca-later", start=8 * RATE)
    p = ops.trim_clip(p, "cv", end=3 * RATE)
    p = ops.move_clip(p, "cv", start=0, track_id="A")

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert q.clip("cv").start == 2 * RATE
    assert q.sync_group("v").main == "v"
    q = ops.move_clip(q, "cv", start=12 * RATE)
    q = ops.resync(q, ["cv"])
    assert q.clip("cv").start == 12 * RATE


def test_align_points_does_not_readd_a_main_moved_to_another_group():
    p, _store = room(offset_frames=0)
    p = ops.add_media(p, Media(id="c", name="c.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_media(p, Media(id="d", name="d.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_track(p, track_id="C", name="C")
    p = ops.add_track(p, track_id="D", name="D")
    p = ops.add_clip(p, track_id="C", media_id="c", clip_id="cc", start=0)
    p = ops.add_clip(p, track_id="D", media_id="d", clip_id="cd", start=0)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g-av")
    p = ops.mark_in_sync(p, ["ca", "cc"], main="cc", group_id="g-ac")

    q = ops.align_points(p, "cv", 0, "cd", 0)

    group_av = q.sync_group("v")
    assert group_av.id == "g-av"
    assert group_av.main == "v"
    assert dict(group_av.members) == {"d": 0, "v": 0}
    assert q.sync_group("a").id == "g-ac"
    assert {group.id for group in q.sync_groups if "a" in dict(group.members)} == {
        "g-ac"
    }


def test_align_points_rejects_sync_frames_outside_the_clip():
    p, _store = room(offset_frames=0)

    with pytest.raises(ops.EditError) as error:
        ops.align_points(p, "ca", 30 * RATE, "cv", 5 * RATE)

    assert error.value.key == "error.edit.sync_point_outside"


def test_align_points_refuses_to_move_before_timeline_start():
    p, _store = room(offset_frames=0)

    with pytest.raises(ops.EditError) as error:
        ops.align_points(p, "ca", RATE, "cv", 2 * RATE)

    assert error.value.key == "error.edit.sync_before_start"


def test_align_points_requires_integer_source_frames():
    p, _store = room(offset_frames=0)

    with pytest.raises(ops.EditError) as error:
        ops.align_points(p, "ca", True, "cv", RATE)

    assert error.value.key == "error.edit.bad_arguments"


def test_resync_puts_moved_clips_back_by_their_timestamps():
    p, _ = marked_room()
    p = ops.move_clip(p, "cv2", start=10 * RATE + 777)
    p = ops.move_clip(p, "cv3", start=20 * RATE - 555)
    q = ops.resync(p, ["cv2", "cv3"])
    assert (q.clip("cv2").start, q.clip("cv3").start) == (10 * RATE, 20 * RATE)


def test_subclips_inherit_the_group():
    p, _ = marked_room()
    assert {group(p, c) for c in ("cv", "cv2", "cv3")} == {"g"}


def test_marking_records_the_offset_as_it_is_now():
    # Ville sits 0.3 s late when marked: that is the truth from then on.
    p, _ = room(offset_frames=int(0.3 * RATE))
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")
    p = ops.move_clip(p, "cv", start=5 * RATE)
    q = ops.resync(p, ["cv"])
    assert q.clip("cv").start == int(0.3 * RATE)


def test_resync_only_touches_the_selection():
    p, _ = marked_room()
    p = ops.move_clip(p, "cv2", start=10 * RATE + 777)
    p = ops.move_clip(p, "cv3", start=20 * RATE - 555)
    q = ops.resync(p, ["cv3"])
    assert q.clip("cv2").start == 10 * RATE + 777
    assert q.clip("cv3").start == 20 * RATE


def test_resync_follows_cuts_in_the_main_clip():
    p, _ = marked_room()
    p = ops.ripple_delete(p, 5 * RATE, 6 * RATE)
    right = next(c for c in p.track("V").clips if c.start == 5 * RATE)
    p = ops.move_clip(p, right.id, start=5 * RATE + 300)
    q = ops.resync(p, [right.id])
    # Against the main clip's piece under it, i.e. after the cut.
    assert q.clip(right.id).start == 5 * RATE


def test_main_clip_and_unsynced_clips_stay_put():
    p, _ = marked_room()
    p = ops.add_track(p, track_id="X", name="X")
    p = ops.add_clip(p, track_id="X", media_id="a", clip_id="loose", start=123)
    q = ops.resync(p, ["ca", "loose"])
    assert q.clip("ca").start == 0
    assert q.clip("loose").start == 123


def test_remarking_moves_whole_files_to_the_new_group():
    p, _ = marked_room()
    p = ops.mark_in_sync(p, ["cv3", "ca"], main="cv3", group_id="h")
    assert {group(p, c) for c in ("ca", "cv", "cv2", "cv3")} == {"h"}


def test_mark_from_clips_still_in_sync_and_fix_ones_never_selected():
    # Never marked. Later in the edit Ville's second piece drifted; the
    # opening pieces are still right, so they are the basis.
    p, _ = room(offset_frames=0)
    p = ops.split_clip(p, "cv", at=10 * RATE, new_id="cv2")
    p = ops.split_clip(p, "ca", at=10 * RATE, new_id="ca2")
    p = ops.move_clip(p, "cv2", start=10 * RATE + 4321)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")
    # Same file, same clock: cv2 joined the group without being selected.
    assert group(p, "cv2") == "g"
    q = ops.resync(p, ["cv2"])
    assert q.clip("cv2").start == 10 * RATE


def test_accidental_one_track_cut_is_fixed_by_resyncing_what_follows():
    p, _ = marked_room()
    # Meant for all tracks, done on Ville's only: everything after slides.
    p = ops.ripple_delete(p, 12 * RATE, 13 * RATE, track_ids=["V"])
    following = ops.clips_from(p, 12 * RATE, track_id="V")
    q = ops.resync(p, following)
    starts = sorted(q.clip(c).start - q.clip(c).offset for c in following)
    # Back on Anna's clock: start - offset is 0 for every piece again...
    assert set(starts) == {0}
    # ...leaving the cut as a visible hole on Ville's track.
    v = q.track("V").clips
    assert any(a.end < b.start for a, b in pairwise(v))


def test_sync_can_be_marked_late_from_the_files_own_timestamps():
    # Never marked; clips were shuffled. The files started together (no
    # time reference: same recorder), so marking by file time restores them.
    p, _ = room(offset_frames=0)
    p = ops.split_clip(p, "cv", at=10 * RATE, new_id="cv2")
    p = ops.move_clip(p, "cv2", start=11 * RATE)
    p = ops.mark_in_sync(p, ["ca", "cv", "cv2"], main="ca", group_id="g",
                         basis="files")
    q = ops.resync(p, ["cv2"])
    assert q.clip("cv2").start == 10 * RATE


def test_marking_by_files_uses_their_time_reference():
    p, _ = room(offset_frames=0)
    ref = frames_to_flicks(int(0.5 * RATE), RATE)
    v = replace(p.media_item("v"), time_ref_flicks=ref)
    p = replace(p, media=tuple(v if m.id == "v" else m for m in p.media))
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g", basis="files")
    q = ops.resync(p, ["cv"])
    # Ville's recorder started 0.5 s later: his frame 0 is Anna's 0.5 s.
    assert q.clip("cv").start == int(0.5 * RATE)


def test_excerpt_inherits_its_originals_sync_origin():
    # A WP20 excerpt of Ville's file from 10 s on: never marked itself, it
    # follows Ville's membership, offset by where it was cut from.
    p, _ = room(offset_frames=int(0.3 * RATE))
    p = ops.add_media(p, Media(id="vx", name="v excerpt", channels=1, frames=5 * RATE,
                               excerpt_of="v",
                               excerpt_start_flicks=frames_to_flicks(10 * RATE, RATE)))
    p = ops.add_clip(p, track_id="V", media_id="vx", clip_id="x", start=99 * RATE)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")
    assert group(p, "x") == "g"
    q = ops.resync(p, ["x"])
    # Excerpt frame 0 is Ville's 10 s, which plays at 10.3 s.
    assert q.clip("x").start == int(10.3 * RATE)


def test_align_points_keeps_surviving_anchor_clock_for_drifted_candidate_piece():
    p, _store = room(offset_frames=0)
    p = ops.add_media(p, Media(id="c", name="c.wav", channels=1, frames=30 * RATE))
    p = ops.add_track(p, track_id="C", name="C")
    p = ops.add_clip(p, track_id="C", media_id="c", clip_id="cc", start=0)
    p = ops.mark_in_sync(p, ["ca", "cc"], main="cc", group_id="g")
    p = ops.delete_clip(p, "cc")
    p = ops.split_clip(p, "ca", at=3 * RATE, new_id="ca-later")
    p = ops.trim_clip(p, "ca", start=2 * RATE)
    p = ops.split_clip(p, "cv", at=3 * RATE, new_id="cv-later")
    p = ops.move_clip(p, "cv-later", start=12 * RATE)
    p = ops.move_clip(p, "cv", start=0, track_id="A")

    q = ops.align_points(p, "ca", 2 * RATE, "cv", 0)

    assert all(c.id != "ca" for track in q.tracks for c in track.clips)
    assert q.sync_group("v").main == "a"
    assert q.clip("cv-later").start == 12 * RATE
    q = ops.resync(q, ["cv-later"])
    assert q.clip("cv-later").start == 5 * RATE


def test_resync_ignores_a_displaced_anchor_piece_overlapping_the_candidate():
    # Devin review on #196: anchor A split 0-2/2-3/3-7/7-30 with the 3-7 piece
    # moved away to t=8; aligning candidate B over the selected 2-3 piece keeps
    # A's clock (the 7-30 piece survives unchanged). Resyncing B's 3-6 piece
    # must follow that clock, not the displaced 3-7 piece that overlaps it.
    p, _store = room(offset_frames=0)
    p = ops.add_media(p, Media(id="c", name="c.wav", channels=1,
                               frames=30 * RATE))
    p = ops.add_track(p, track_id="C", name="C")
    p = ops.add_clip(p, track_id="C", media_id="c", clip_id="cc", start=0)
    p = ops.mark_in_sync(p, ["ca", "cc"], main="cc", group_id="g")
    p = ops.delete_clip(p, "cc")
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca-pick")
    p = ops.split_clip(p, "ca-pick", at=3 * RATE, new_id="ca-mid")
    p = ops.split_clip(p, "ca-mid", at=7 * RATE, new_id="ca-late")
    p = ops.move_clip(p, "ca-mid", start=8 * RATE, track_id="C")
    p = ops.split_clip(p, "cv", at=3 * RATE, new_id="cv-mid")
    p = ops.split_clip(p, "cv-mid", at=6 * RATE, new_id="cv-late")
    p = ops.move_clip(p, "cv", start=0, track_id="A")

    q = ops.align_points(p, "ca-pick", 2 * RATE, "cv", 0)

    assert q.sync_group("v").main == "a"
    q = ops.move_clip(q, "cv-mid", start=12 * RATE)
    q = ops.resync(q, ["cv-mid"])
    assert q.clip("cv-mid").start == 5 * RATE


def test_resync_keeps_pieces_before_a_group_wide_cut_on_their_clock():
    # Devin review on the #196 fix: a group-wide ripple cut gives the pieces
    # after it a new shared clock; the pieces before it are still right and
    # must not be dropped from the reference choice for being outnumbered.
    p, _ = marked_room()
    p = ops.split_clip(p, "ca", at=10 * RATE, new_id="ca2")
    p = ops.split_clip(p, "ca2", at=20 * RATE, new_id="ca3")
    p = ops.split_clip(p, "cv", at=2 * RATE, new_id="cv0")
    p = ops.ripple_delete(p, 5 * RATE, 6 * RATE)
    before_cut = next(c for c in p.track("V").clips if c.start == 2 * RATE)

    q = ops.resync(p, [before_cut.id])

    assert q.clip(before_cut.id).start == 2 * RATE


def test_resync_ignores_a_displaced_edge_piece_of_the_main_clip():
    # Devin review on the #196 fix: an edge piece dragged off on its own must
    # not win the reference either; the surviving pieces keep the clock.
    p, _ = marked_room()
    p = ops.add_track(p, track_id="X", name="X")
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca-mid")
    p = ops.split_clip(p, "ca-mid", at=7 * RATE, new_id="ca-late")
    p = ops.move_clip(p, "ca", start=8 * RATE, track_id="X")
    p = ops.split_clip(p, "cv", at=2 * RATE, new_id="cv-rest")

    q = ops.resync(p, ["cv"])

    assert q.clip("cv").start == 0


def test_resync_keeps_trailing_reference_after_a_cut_across_a_trim_gap():
    # Devin review on the #196 fix: a trim opens a source gap; a group-wide
    # cut across it shifts the trailing piece and its partner together, and
    # the trailing piece must stay a reference though it abuts nothing.
    p, _ = marked_room()
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca2")
    p = ops.split_clip(p, "ca2", at=7 * RATE, new_id="ca3")
    p = ops.trim_clip(p, "ca2", end=5 * RATE)
    p = ops.split_clip(p, "cv", at=7 * RATE, new_id="cv-tail")
    p = ops.ripple_delete(p, 5 * RATE, 6 * RATE)
    assert p.clip("cv-tail").start == 6 * RATE

    q = ops.resync(p, ["cv-tail"])

    assert q.clip("cv-tail").start == 6 * RATE


def test_resync_ignores_a_piece_abutting_a_trimmed_neighbour():
    # Devin review on the #196 fix: timeline abutment with a trimmed neighbour
    # is not coherence - the source ranges do not touch, so the dragged piece
    # is displaced even though it touches another piece on the timeline.
    p, _ = marked_room()
    p = ops.add_track(p, track_id="X", name="X")
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca-mid")
    p = ops.split_clip(p, "ca-mid", at=4 * RATE, new_id="ca-late")
    p = ops.trim_clip(p, "ca", end=1 * RATE)
    p = ops.move_clip(p, "ca-mid", start=1 * RATE, track_id="X")
    p = ops.split_clip(p, "cv", at=2 * RATE, new_id="cv-mid")
    p = ops.split_clip(p, "cv-mid", at=4 * RATE, new_id="cv-rest")
    p = ops.move_clip(p, "cv-mid", start=12 * RATE)

    q = ops.resync(p, ["cv-mid"])

    assert q.clip("cv-mid").start == 2 * RATE


def test_resync_follows_a_coherently_moved_block_of_the_main_clip():
    # Devin review on the #196 fix: a block of pieces moved together keeps its
    # clock, even when more pieces stay behind; their partners follow them.
    p, _ = marked_room()
    p = ops.add_track(p, track_id="X", name="X")
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca-b1")
    p = ops.split_clip(p, "ca-b1", at=4 * RATE, new_id="ca-b2")
    p = ops.split_clip(p, "ca-b2", at=6 * RATE, new_id="ca-c1")
    p = ops.split_clip(p, "ca-c1", at=8 * RATE, new_id="ca-c2")
    p = ops.move_clip(p, "ca-b1", start=32 * RATE, track_id="X")
    p = ops.move_clip(p, "ca-b2", start=34 * RATE, track_id="X")
    p = ops.split_clip(p, "cv", at=4 * RATE, new_id="cv-rest")
    p = ops.split_clip(p, "cv", at=2 * RATE, new_id="cv-mid")

    q = ops.resync(p, ["cv-mid"])

    assert q.clip("cv-mid").start == 32 * RATE


def test_resync_ignores_an_edge_piece_shifted_into_a_trim_gap():
    # Devin review on the #196 fix: a cut can only shift later content, so a
    # lone leading piece off the recording's clock was dragged, even when its
    # move only shortened a gap a trim opened.
    p, _ = marked_room()
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca-mid")
    p = ops.split_clip(p, "ca-mid", at=4 * RATE, new_id="ca-late")
    p = ops.trim_clip(p, "ca-mid", start=3 * RATE)
    p = ops.move_clip(p, "ca", start=RATE // 2)
    p = ops.split_clip(p, "cv", at=2 * RATE, new_id="cv-rest")
    p = ops.move_clip(p, "cv", start=12 * RATE)

    q = ops.resync(p, ["cv"])

    assert q.clip("cv").start == 0


def test_resync_ignores_a_lone_trailing_piece_dragged_later():
    # Devin review on the #196 fix: a trailing piece dragged off on its own
    # keeps a clock no other recording in the group keeps; partners stay on
    # the clock the rest of the group agrees on.
    p, _ = marked_room()
    p = ops.split_clip(p, "ca", at=2 * RATE, new_id="ca-mid")
    p = ops.split_clip(p, "ca-mid", at=4 * RATE, new_id="ca-tail")
    p = ops.trim_clip(p, "ca-tail", end=6 * RATE)
    p = ops.move_clip(p, "ca-tail", start=9 * RATE)
    p = ops.split_clip(p, "cv", at=4 * RATE, new_id="cv-tail")
    p = ops.trim_clip(p, "cv-tail", end=6 * RATE)

    q = ops.resync(p, ["cv-tail"])

    assert q.clip("cv-tail").start == 4 * RATE


def test_resync_keeps_a_trailing_piece_shifted_with_the_whole_group():
    # The mirror image: a group-wide insert shifts the trailing pieces of
    # every recording together, so the shifted trailing piece stays the
    # reference for its range.
    p, _ = marked_room()
    p = ops.split_clip(p, "ca", at=4 * RATE, new_id="ca-tail")
    p = ops.split_clip(p, "cv", at=4 * RATE, new_id="cv-tail")
    for clip_id, start in (("ca-tail", 9 * RATE), ("cv-tail", 9 * RATE),
                           ("cv2", 15 * RATE), ("cv3", 25 * RATE)):
        p = ops.move_clip(p, clip_id, start=start)

    q = ops.resync(p, ["cv-tail"])

    assert q.clip("cv-tail").start == 9 * RATE


def test_resync_fixes_a_partner_piece_drifted_onto_the_tails_clock():
    # Devin review on the #196 fix: the clip being resynced must not testify
    # against its own reference; a drifted opening follows the opening, not
    # the shifted tail it happens to share a clock with.
    p, _ = marked_room()
    p = ops.split_clip(p, "ca", at=4 * RATE, new_id="ca-tail")
    p = ops.split_clip(p, "cv", at=4 * RATE, new_id="cv-tail")
    p = ops.move_clip(p, "ca-tail", start=9 * RATE)
    p = ops.move_clip(p, "cv-tail", start=9 * RATE)
    p = ops.move_clip(p, "cv2", start=15 * RATE)
    p = ops.move_clip(p, "cv3", start=25 * RATE)
    p = ops.move_clip(p, "cv", start=5 * RATE)

    q = ops.resync(p, ["cv"])

    assert q.clip("cv").start == 0


def test_resync_with_offset_recordings_compares_witnesses_in_recording_time():
    # Devin review on the #196 fix: a partner that started 2 s after the main
    # has raw source offsets 2 s behind the group clock; they must not
    # witness against the main's untouched opening piece.
    p, _store = room(offset_frames=2 * RATE)
    p = ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")
    p = ops.split_clip(p, "ca", at=4 * RATE, new_id="ca-tail")
    p = ops.split_clip(p, "cv", at=4 * RATE, new_id="cv-tail")
    p = ops.move_clip(p, "ca-tail", start=9 * RATE)
    p = ops.move_clip(p, "cv-tail", start=9 * RATE)

    q = ops.resync(p, ["cv"])

    assert q.clip("cv").start == 2 * RATE
