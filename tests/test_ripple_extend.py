"""Giving material back at a splice on every track at once (owner, 2026-10-19).

At about 33 minutes a stretch had been cut from three parallel tracks. Dragging one
clip's end edge outwards with Shift (a ripple trim) gives the material back on that
track; with ``extend_partners`` the other tracks' clips that end at the same splice
grow by the same amount, so nothing is left as silence on them.
"""

from kuulas import ops
from kuulas.model import Media, Project

RATE = 48000
S = RATE


def three_tracks(*, media_frames=60 * S, second_media=None) -> Project:
    """T1..T3: a left clip 0..10 s (source 0..10 s) and a right clip 10..20 s whose
    source starts at 15 s: 5 s of the recording (10..15 s) were cut out at the splice."""
    p = Project(rate=RATE)
    for t in ("1", "2", "3"):
        frames = (second_media or media_frames) if t == "2" else media_frames
        media = Media(id=f"m{t}", name=f"m{t}.wav", channels=1, frames=frames)
        p = ops.add_media(p, media)
        p = ops.add_track(p, track_id=f"T{t}", name=f"T{t}")
        p = ops.add_clip(p, f"T{t}", f"m{t}", start=0, length=10 * S, clip_id=f"L{t}")
        short = second_media is not None and t == "2"
        offset, length = (frames - S, S) if short else (15 * S, 10 * S)
        p = ops.add_clip(p, f"T{t}", f"m{t}", start=10 * S, offset=offset, length=length,
                         clip_id=f"R{t}")
    return p


def span(p: Project, clip_id: str) -> tuple[int, int]:
    clip = next(c for t in p.tracks for c in t.clips if c.id == clip_id)
    return clip.start, clip.end


def test_the_other_tracks_clips_that_end_at_the_splice_grow_by_the_same_amount():
    p = ops.ripple_trim(three_tracks(), "L1", "end", 13 * S, extend_partners=True)
    assert span(p, "L1") == (0, 13 * S)
    assert span(p, "L2") == (0, 13 * S)
    assert span(p, "L3") == (0, 13 * S)
    assert span(p, "R1") == (13 * S, 23 * S)  # everything after moves by the same 3 s
    assert span(p, "R2") == (13 * S, 23 * S)


def test_a_track_that_runs_out_of_source_is_extended_as_far_as_it_can():
    p = three_tracks(second_media=12 * S)
    p = ops.ripple_trim(p, "L1", "end", 13 * S, extend_partners=True)
    assert span(p, "L2") == (0, 12 * S)  # its recording ends at 12 s
    assert span(p, "L3") == (0, 13 * S)


def test_a_clip_that_does_not_end_at_the_splice_is_left_alone():
    p = three_tracks()
    p = ops.trim_clip(p, "L3", end=7 * S)  # T3 was cut elsewhere
    p = ops.ripple_trim(p, "L1", "end", 13 * S, extend_partners=True)
    assert span(p, "L3") == (0, 7 * S)


def test_without_the_flag_the_other_tracks_get_a_gap_as_before():
    p = ops.ripple_trim(three_tracks(), "L1", "end", 13 * S)
    assert span(p, "L2") == (0, 10 * S)
    assert span(p, "R2") == (13 * S, 23 * S)


def test_a_shorter_clip_ignores_the_flag():
    p = ops.ripple_trim(three_tracks(), "L1", "end", 8 * S, extend_partners=True)
    assert span(p, "L1") == (0, 8 * S)
    assert span(p, "L2") == (0, 8 * S)  # the ripple delete took it from every track
