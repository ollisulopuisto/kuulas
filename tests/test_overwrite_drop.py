"""Dropping or nudging a clip on others overwrites what is under it (owner, 2026-10-18).

Clips on one track never overlap after a move (there are no layers): the clips under the
moved one are trimmed, split around it, or removed when fully covered. Nothing is lost, a
trimmed clip still points at its whole source, and the whole move is one edit.
"""

from itertools import pairwise

from kuulas import ops
from kuulas.model import Media, Project

RATE = 48000
S = RATE
TO_T = -(20 * S)  # X sits at 20 s on U: this plus the target start is its delta


def base(*, long_start=0, long_len=10 * S) -> Project:
    """A long clip ``L`` on track T; a short clip ``X`` (2 s) at 20 s on track U."""
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=60 * S))
    for t in ("T", "U"):
        p = ops.add_track(p, track_id=t, name=t)
    p = ops.add_clip(p, "T", "m", start=long_start, length=long_len, clip_id="L")
    return ops.add_clip(p, "U", "m", start=20 * S, length=2 * S, clip_id="X")


def spans(p: Project, track_id: str) -> list[tuple[str, int, int]]:
    track = next(t for t in p.tracks if t.id == track_id)
    return [(c.id, c.start, c.end) for c in track.clips]


def no_overlaps(p: Project) -> bool:
    for track in p.tracks:
        clips = sorted(track.clips, key=lambda c: c.start)
        if any(a.end > b.start for a, b in pairwise(clips)):
            return False
    return True


def drop_x_at(p: Project, start: int, **kwargs) -> Project:
    """Move X one track up (onto T) so that it starts at ``start``."""
    return ops.move_clips_to_track(p, ["X"], -1, delta=TO_T + start, **kwargs)


def test_a_short_clip_dropped_inside_a_long_one_splits_it_around_the_short():
    p = drop_x_at(base(), 4 * S)  # 4 s .. 6 s on T
    clips = spans(p, "T")
    assert ("X", 4 * S, 6 * S) in clips
    pieces = sorted(c for c in clips if c[0] != "X")
    assert [(s, e) for _, s, e in pieces] == [(0, 4 * S), (6 * S, 10 * S)]
    assert no_overlaps(p)


def test_the_right_piece_keeps_playing_the_same_audio():
    p = drop_x_at(base(), 4 * S)
    track = next(t for t in p.tracks if t.id == "T")
    right = next(c for c in track.clips if c.id != "X" and c.start == 6 * S)
    assert right.offset == 6 * S  # the source frame at 6 s, as before


def test_covering_one_end_trims_that_end():
    p = drop_x_at(base(), 9 * S)  # 9 s .. 11 s, over L's end
    assert [(s, e) for i, s, e in spans(p, "T") if i == "L"] == [(0, 9 * S)]
    assert no_overlaps(p)


def test_a_fully_covered_clip_is_removed():
    p = base(long_start=5 * S, long_len=S)  # L is 5 s .. 6 s
    p = drop_x_at(p, 4 * S + S // 2)  # X lands on 4.5 s .. 6.5 s
    assert [c[0] for c in spans(p, "T")] == ["X"]


def test_moving_without_overwrite_keeps_the_overlap():
    p = drop_x_at(base(), 4 * S, overwrite=False)
    assert not no_overlaps(p)
    assert {c[0] for c in spans(p, "T")} == {"L", "X"}


def test_a_move_in_time_on_its_own_track_also_overwrites_neighbours():
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=60 * S))
    p = ops.add_track(p, track_id="T", name="T")
    p = ops.add_clip(p, "T", "m", start=0, length=4 * S, clip_id="A")
    p = ops.add_clip(p, "T", "m", start=10 * S, length=4 * S, clip_id="B")
    p = ops.move_clips_to_track(p, ["B"], 0, delta=-(8 * S))  # B: 2 s .. 6 s
    assert spans(p, "T") == [("A", 0, 2 * S), ("B", 2 * S, 6 * S)]


def test_a_keyboard_nudge_over_a_neighbour_overwrites_it_too():
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=60 * S))
    p = ops.add_track(p, track_id="T", name="T")
    p = ops.add_clip(p, "T", "m", start=0, length=4 * S, clip_id="A")
    p = ops.add_clip(p, "T", "m", start=5 * S, length=2 * S, clip_id="B")
    p = ops.nudge_clips(p, ["B"], -(2 * S))  # B to 3 s .. 5 s, over A's end
    assert spans(p, "T") == [("A", 0, 3 * S), ("B", 3 * S, 5 * S)]


def test_clips_that_were_not_moved_are_left_alone():
    p = ops.move_clips_to_track(base(), ["X"], 0, delta=S)  # only a nudge on U
    assert spans(p, "T") == [("L", 0, 10 * S)]
