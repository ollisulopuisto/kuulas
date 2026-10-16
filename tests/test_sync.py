"""Auto-sync: put a clip back in time with the rest of the room.

Two mics in one room hear each other, so the bleed on one is a delayed,
quieter copy of the other's speech; correlating the two finds the offset.
"""

from dataclasses import replace
from itertools import pairwise

import numpy as np

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
