"""Tests for timeline snapping."""

from __future__ import annotations

import itertools

from kuulas.model import Clip, Project, Track
from kuulas.snap import snap_targets, snap_to, soft_snap


def _project(*clips: Clip, rate: int = 48000) -> Project:
    return Project(
        rate=rate,
        tracks=(Track(id="t1", name="Track 1", clips=tuple(clips)),),
    )


class TestSnapTargets:
    def test_empty_project_gives_empty_targets(self):
        project = Project()
        assert snap_targets(project) == ()

    def test_unmuted_clip_edges_are_included(self):
        project = _project(Clip(id="c1", media="m1", start=100, offset=0, length=200))
        assert snap_targets(project) == (100, 300)

    def test_muted_clip_edges_are_left_out(self):
        project = _project(
            Clip(id="c1", media="m1", start=100, offset=0, length=200),
            Clip(id="c2", media="m1", start=400, offset=0, length=100, muted=True),
        )
        assert snap_targets(project) == (100, 300)

    def test_excluded_clips_are_left_out(self):
        a = Clip(id="a", media="m1", start=100, offset=0, length=200)
        b = Clip(id="b", media="m1", start=400, offset=0, length=100)
        project = _project(a, b)
        assert snap_targets(project, exclude_clips=("a",)) == (400, 500)

    def test_playhead_and_in_out_are_included(self):
        project = _project(Clip(id="c1", media="m1", start=100, offset=0, length=200))
        assert snap_targets(project, playhead=150, in_out=(50, 350)) == (
            50,
            100,
            150,
            300,
            350,
        )

    def test_grid_multiples_up_to_project_length(self):
        project = _project(Clip(id="c1", media="m1", start=0, offset=0, length=100))
        assert snap_targets(project, grid=30) == (0, 30, 60, 90, 100)

    def test_grid_without_clip_edges(self):
        project = _project(Clip(id="c1", media="m1", start=0, offset=0, length=100))
        assert snap_targets(project, kinds=("grid",), grid=40) == (0, 40, 80)

    def test_results_are_sorted_and_deduplicated(self):
        project = _project(Clip(id="c1", media="m1", start=100, offset=0, length=200))
        assert snap_targets(project, playhead=100, grid=100) == (0, 100, 200, 300)


class TestSnapTo:
    def test_nearest_target_wins(self):
        targets = (0, 100, 200)
        assert snap_to(85, targets, 20) == (100, 100)

    def test_tie_goes_to_lower_frame(self):
        targets = (0, 100, 200)
        assert snap_to(110, targets, 20) == (100, 100)

    def test_outside_threshold_returns_raw_frame(self):
        targets = (0, 100, 200)
        assert snap_to(85, targets, 10) == (85, None)

    def test_empty_targets_returns_raw_frame(self):
        assert snap_to(50, (), 10) == (50, None)

    def test_exact_match_snaps(self):
        targets = (0, 100, 200)
        assert snap_to(100, targets, 0) == (100, 100)


class TestSoftSnap:
    def test_soft_snap_snaps_within_threshold(self):
        targets = (0, 100, 200)
        assert soft_snap(90, targets, 20, hold_frames=15) == (100, 100)

    def test_soft_snap_releases_beyond_hold_frames(self):
        targets = (0, 100, 200)
        assert soft_snap(117, targets, 20, hold_frames=15) == (117, None)

    def test_soft_snap_still_snaps_when_not_past_target(self):
        targets = (0, 100, 200)
        assert soft_snap(108, targets, 20, hold_frames=15) == (100, 100)

    def test_soft_snap_no_target_returns_raw_frame(self):
        targets = (0, 100, 200)
        assert soft_snap(85, targets, 10, hold_frames=5) == (85, None)


def test_a_tiny_grid_on_a_long_project_stays_bounded():
    p = Project(rate=48000, tracks=(Track(id="t1", name="a", clips=(
        Clip(id="c", media="m", start=0, offset=0, length=48000 * 3600),)),))
    targets = snap_targets(p, kinds=("grid",), grid=1)
    assert len(targets) <= 100_001
    assert targets[0] == 0
    steps = {b - a for a, b in itertools.pairwise(targets)}
    assert len(steps) == 1
