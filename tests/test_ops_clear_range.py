"""ops.clear_range: delete ``[start, end)``, leave the gap (lift-cut, 2026-10-19)."""

import pytest

from kuulas import ops
from kuulas.model import Clip, Project, Track

RATE = 48000


def project():
    tracks = (
        Track(id="t1", name="A", clips=(
            Clip(id="c1", media="m", start=0, length=100, offset=0),)),
        Track(id="t2", name="B", clips=(
            Clip(id="c2", media="m", start=0, length=100, offset=500),)),
    )
    return Project(rate=RATE, tracks=tracks)


def spans(p, track):
    return [(c.start, c.length, c.offset)
            for t in p.tracks if t.id == track for c in t.clips]


def test_a_range_inside_a_clip_leaves_two_pieces_and_a_gap():
    out = ops.clear_range(project(), 30, 60, ["t1"])
    assert spans(out, "t1") == [(0, 30, 0), (60, 40, 60)]
    assert spans(out, "t2") == [(0, 100, 500)]  # other tracks untouched


def test_nothing_moves_and_the_audio_keeps_its_place():
    out = ops.clear_range(project(), 30, 60, ["t1", "t2"])
    assert spans(out, "t2") == [(0, 30, 500), (60, 40, 560)]


def test_a_range_over_a_clip_edge_trims_it():
    out = ops.clear_range(project(), 80, 150, ["t1"])
    assert spans(out, "t1") == [(0, 80, 0)]
    out = ops.clear_range(project(), 0, 40, ["t1"])
    assert spans(out, "t1") == [(40, 60, 40)]


def test_a_range_covering_a_clip_removes_it():
    assert spans(ops.clear_range(project(), 0, 100, ["t1"]), "t1") == []


def test_an_empty_range_is_an_error():
    with pytest.raises(ops.EditError):
        ops.clear_range(project(), 10, 10, ["t1"])
