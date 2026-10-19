"""Muted and gated stretches of a track on the stem's own clock (WP85 step 1)."""

from dataclasses import replace

from kuulas.model import Clip, Track
from kuulas.stem_ranges import gate_ranges, muted_ranges, on_stem_clock


def clip(start, length, muted=False):
    return Clip(id=f"c{start}", media="m", start=start, offset=0, length=length,
                muted=muted)


def track(clips, gate=()):
    return replace(Track(id="t", name="t"), clips=tuple(clips), gate=tuple(gate))


def test_on_stem_clock_offsets_clips_and_merges():
    assert on_stem_clock([(30, 40), (10, 20), (20, 25)], 5, 100) == [[5, 20], [25, 35]]


def test_on_stem_clock_clips_both_ends():
    assert on_stem_clock([(0, 12), (40, 200)], 10, 50) == [[0, 2], [30, 50]]


def test_on_stem_clock_drops_ranges_outside_and_empty():
    assert on_stem_clock([(0, 10), (60, 70), (20, 20)], 10, 50) == []
    assert on_stem_clock([], 0, 50) == []


def test_touching_ranges_are_one():
    assert on_stem_clock([(0, 10), (10, 20)], 0, 100) == [[0, 20]]


def test_muted_ranges_use_only_muted_clips_and_join_touching_ones():
    t = track([clip(0, 10), clip(10, 10, True), clip(20, 5, True), clip(30, 10),
               clip(40, 10, True)], gate=[(0, 5)])
    assert muted_ranges(t, 0, 100) == [[10, 25], [40, 50]]


def test_muted_ranges_offset_by_first():
    t = track([clip(100, 50, True)])
    assert muted_ranges(t, 120, 100) == [[0, 30]]


def test_track_without_muted_clips_has_none():
    assert muted_ranges(track([clip(0, 10)]), 0, 100) == []


def test_gate_kept_apart_from_mutes():
    t = track([clip(0, 10, True)], gate=[(20, 30), (30, 35), (95, 200)])
    assert gate_ranges(t, 5, 90) == [[15, 30]]
    assert muted_ranges(t, 5, 90) == [[0, 5]]
