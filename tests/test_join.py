"""Tests for joining adjacent clips."""

from __future__ import annotations

from kuulas.join import join_adjacent
from kuulas.model import Clip


def _clip(
    start: int,
    length: int,
    offset: int = 0,
    *,
    media: str = "m1",
    id: str = "c",
    gain_db: float = 0.0,
    pan: float = 0.0,
    muted: bool = False,
    fade_in: int = 0,
    fade_out: int = 0,
    envelope: tuple[tuple[int, float], ...] = (),
    xfade_in: int = 0,
    xfade_out: int = 0,
) -> Clip:
    return Clip(
        id=id,
        media=media,
        start=start,
        offset=offset,
        length=length,
        gain_db=gain_db,
        pan=pan,
        fade_in=fade_in,
        fade_out=fade_out,
        muted=muted,
        envelope=envelope,
        xfade_in=xfade_in,
        xfade_out=xfade_out,
    )


class TestJoinAdjacent:
    def test_three_contiguous_pieces_become_one(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        b = _clip(start=100, length=50, offset=100, id="b")
        c = _clip(start=150, length=75, offset=150, id="c")
        result = join_adjacent([a, b, c])
        assert result == [
            _clip(start=0, length=225, offset=0, id="a"),
        ]

    def test_gap_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        b = _clip(start=110, length=50, offset=100, id="b")
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_source_jump_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        b = _clip(start=100, length=50, offset=105, id="b")
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_different_gain_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a", gain_db=1.0)
        b = _clip(start=100, length=50, offset=100, id="b", gain_db=2.0)
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_different_pan_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a", pan=-0.5)
        b = _clip(start=100, length=50, offset=100, id="b", pan=0.5)
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_different_muted_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a", muted=True)
        b = _clip(start=100, length=50, offset=100, id="b", muted=False)
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_envelope_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a", envelope=((10, -3.0),))
        b = _clip(start=100, length=50, offset=100, id="b")
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_crossfade_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a", xfade_out=20)
        b = _clip(start=100, length=50, offset=100, id="b")
        result = join_adjacent([a, b])
        assert result == [a, b]

        c = _clip(start=0, length=100, offset=0, id="c")
        d = _clip(start=100, length=50, offset=100, id="d", xfade_in=20)
        result = join_adjacent([c, d])
        assert result == [c, d]

    def test_two_runs_join_separately(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        b = _clip(start=100, length=50, offset=100, id="b")
        c = _clip(start=200, length=75, offset=200, id="c")
        d = _clip(start=275, length=25, offset=275, id="d")
        result = join_adjacent([a, b, c, d])
        assert result == [
            _clip(start=0, length=150, offset=0, id="a"),
            _clip(start=200, length=100, offset=200, id="c"),
        ]

    def test_single_clip_unchanged(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        result = join_adjacent([a])
        assert result == [a]

    def test_input_not_modified(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        b = _clip(start=100, length=50, offset=100, id="b")
        original = [a, b]
        join_adjacent(original)
        assert original == [a, b]
        assert original[0] is a
        assert original[1] is b

    def test_result_sorted_by_start(self):
        a = _clip(start=0, length=100, offset=0, id="a", media="m1")
        b = _clip(start=100, length=50, offset=0, id="b", media="m2")
        result = join_adjacent([b, a])
        assert result == [a, b]
        assert [c.start for c in result] == [0, 100]

    def test_keeps_first_fade_in_and_last_fade_out(self):
        a = _clip(start=0, length=100, offset=0, id="a", fade_in=5)
        b = _clip(start=100, length=50, offset=100, id="b")
        c = _clip(start=150, length=75, offset=150, id="c", fade_out=7)
        result = join_adjacent([a, b, c])
        assert result == [
            _clip(start=0, length=225, offset=0, id="a", fade_in=5, fade_out=7),
        ]

    def test_keeps_outer_crossfades(self):
        a = _clip(start=0, length=100, offset=0, id="a", xfade_in=10)
        b = _clip(start=100, length=50, offset=100, id="b")
        c = _clip(start=150, length=75, offset=150, id="c", xfade_out=20)
        result = join_adjacent([a, b, c])
        expected = _clip(
            start=0,
            length=225,
            offset=0,
            id="a",
            xfade_in=10,
            xfade_out=20,
        )
        assert result == [expected]

    def test_different_media_stops_join(self):
        a = _clip(start=0, length=100, offset=0, id="a", media="m1")
        b = _clip(start=100, length=50, offset=100, id="b", media="m2")
        result = join_adjacent([a, b])
        assert result == [a, b]

    def test_empty_input(self):
        assert join_adjacent([]) == []

    def test_overlap_does_not_join(self):
        a = _clip(start=0, length=100, offset=0, id="a")
        b = _clip(start=90, length=50, offset=100, id="b")
        result = join_adjacent([a, b])
        assert result == [a, b]
