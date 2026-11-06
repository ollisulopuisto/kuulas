"""Bounded interval checks against an independent integer-frame occupancy oracle."""

import os
import random

import pytest

from kuulas.clip_gaps import clip_gaps

SEED = int(os.environ.get("FUZZ_SEED", "20261106"))


@pytest.mark.parametrize("seed", [SEED, SEED + 1, SEED + 2])
def test_interval_coverage_conservation_and_invariance(seed):
    rng = random.Random(seed)  # noqa: S311 - reproducible offline interval fixtures, no secrets
    for case in range(120):
        clips = []
        for _ in range(rng.randrange(1, 20)):
            start = rng.randrange(-20, 40)
            clips.append((start, start + rng.randrange(1, 30)))
        before = list(clips)
        result = clip_gaps(clips)
        context = f"seed={seed} case={case} clips={clips!r}"
        # Integer half-open intervals: each cell is exactly one model frame.
        left = min(start for start, _ in clips)
        right = max(end for _, end in clips)
        occupancy = [
            sum(start <= frame < end for start, end in clips)
            for frame in range(left, right)
        ]
        missing = {left + i for i, count in enumerate(occupancy) if count == 0}
        reported = {frame for start, end in result["gaps"] for frame in range(start, end)}
        assert reported == missing, context
        assert sum(end - start for start, end in result["overlaps"]) == sum(
            max(0, count - 1) for count in occupancy
        ), context
        assert clips == before, context
        rng.shuffle(clips)
        assert clip_gaps(clips) == result, context
        shift = rng.randrange(-1000, 1000)
        moved = clip_gaps([(start + shift, end + shift) for start, end in clips])
        assert moved == {
            key: [(start + shift, end + shift) for start, end in spans]
            for key, spans in result.items()
        }, context


def test_nested_interval_regression():
    assert clip_gaps([(0, 30), (5, 10), (20, 40), (50, 60)]) == {
        "gaps": [(40, 50)],
        "overlaps": [(5, 10), (20, 30)],
    }
