"""M on a stretch Auto-Silence closed (owner, 2026-10-23, BUGS #109): only THAT stretch
opens, as a clip of its own; the parent clip is not touched as a whole."""

import pytest

from kuulas import ops
from kuulas.model import Clip, Media, Project, Track
from kuulas.ops import EditError

RATE = 48_000


def fr(seconds):
    return round(seconds * RATE)


def project(clips, gate, *, mute_all=False):
    media = (Media("a", "a.wav", 1, fr(20), sha256="a" * 64),)
    track = Track("t", "Voice", clips=tuple(clips), gate=tuple(gate))
    return Project(rate=RATE, media=media, tracks=(track,))


def whole(**kw):
    return Clip("c", "a", 0, 0, fr(10), **kw)


def pieces(p):
    return [(c.start, c.end, c.ungated, c.muted)
            for c in sorted(p.tracks[0].clips, key=lambda c: c.start)]


def test_the_closed_stretch_becomes_its_own_open_clip():
    p = project([whole()], [(fr(4), fr(6))])
    q = ops.open_gated_region(p, "t", fr(5))
    assert pieces(q) == [(0, fr(4), False, False), (fr(4), fr(6), True, False),
                         (fr(6), fr(10), False, False)]


def test_the_gate_is_open_under_the_new_clip_and_closed_elsewhere():
    p = project([whole()], [(fr(1), fr(2)), (fr(4), fr(6))])
    q = ops.open_gated_region(p, "t", fr(5))
    assert q.tracks[0].gate == ((fr(1), fr(2)),)


def test_the_pieces_keep_playing_the_same_audio():
    p = project([whole()], [(fr(4), fr(6))])
    q = ops.open_gated_region(p, "t", fr(5))
    middle = next(c for c in q.tracks[0].clips if c.ungated)
    assert (middle.offset, middle.length) == (fr(4), fr(2))


def test_a_stretch_across_two_clips_opens_a_piece_of_each():
    p = project([Clip("c1", "a", 0, 0, fr(5)), Clip("c2", "a", fr(5), fr(5), fr(5))],
                [(fr(4), fr(6))])
    q = ops.open_gated_region(p, "t", fr(5))
    assert pieces(q) == [(0, fr(4), False, False), (fr(4), fr(5), True, False),
                         (fr(5), fr(6), True, False), (fr(6), fr(10), False, False)]


def test_a_stretch_that_starts_at_the_clip_start_makes_no_empty_piece():
    p = project([whole()], [(0, fr(3))])
    q = ops.open_gated_region(p, "t", fr(1))
    assert pieces(q) == [(0, fr(3), True, False), (fr(3), fr(10), False, False)]


def test_a_muted_clip_under_the_stretch_is_unmuted_there_only():
    p = project([whole(muted=True)], [(fr(4), fr(6))])
    q = ops.open_gated_region(p, "t", fr(5))
    assert pieces(q) == [(0, fr(4), False, True), (fr(4), fr(6), True, False),
                         (fr(6), fr(10), False, True)]


def test_outside_a_closed_stretch_there_is_nothing_to_open():
    p = project([whole()], [(fr(4), fr(6))])
    with pytest.raises(EditError):
        ops.open_gated_region(p, "t", fr(7))
    with pytest.raises(EditError):
        ops.open_gated_region(project([whole()], []), "t", fr(5))


def test_the_op_is_in_the_table_and_runs_by_name():
    p = project([whole()], [(fr(4), fr(6))])
    q = ops.apply(p, "open_gated_region", {"track_id": "t", "at": fr(5)})
    assert any(c.ungated for c in q.tracks[0].clips)
