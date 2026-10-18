"""Scrubbing at tape speed costs one mix per block, never a burst (WP26).

Owner's debug log, 2026-10-18: scrubbing backwards with J at several times
speed, the callback's worst block grew from 11 to 22 ms (a block lasts 21.3
ms) until the engine raised its buffer. Cause, found by profiling: when the
resampler's queue was a few frames short, the render loop asked the
resampler for ``ceil(shortfall * speed)`` input frames, a handful. soxr
answers a handful of input frames with no output at all, so the loop went
round again and again (up to 489 times in one block, each time mixing all
tracks) until enough had come out. A block in that state took 30 ms.

The guard is a count, not a clock: mixes per rendered block. A timing test
with a generous, self-relative budget sits beside it.
"""

import time

import numpy as np
import pytest
from test_engine import (
    RATE,
    Clock,
    FakeSession,
    MemoryStore,
    install_rig,
    noise,
    project_with,
)

from kuulas import mixer, playplan
from kuulas.engine import Engine

BLOCKS = 400
TRACKS = 4


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


def build(clock):
    arrays = {f"m{i}": noise(120, channels=1 + i % 2, seed=i) for i in range(TRACKS)}
    store = MemoryStore(arrays)
    return Engine(FakeSession(project_with(arrays), store), background=False,
                  clock=clock)


class Counter:
    def __init__(self, monkeypatch):
        self.mixes = 0
        real = mixer.mix

        def counting(*args, **kwargs):
            self.mixes += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(playplan.mixer, "mix", counting)


def run_blocks(engine, count=BLOCKS):
    """Per-block (mixes, milliseconds) after a prefetch every 12 blocks."""
    rows = []
    counter = engine._counter
    for i in range(count):
        if i % 12 == 0:
            engine._prefetch()
        before = counter.mixes
        began = time.perf_counter()
        engine._render(1024)
        rows.append((counter.mixes - before, (time.perf_counter() - began) * 1e3))
    return rows


@pytest.mark.parametrize("speed", [-5.0, -4.0, -2.0, -1.5, 1.5, 2.0, 5.0])
def test_a_block_mixes_at_most_twice_at_tape_speed(rig, monkeypatch, speed):
    engine = build(Clock())
    engine._counter = Counter(monkeypatch)
    engine.play(110 * RATE if speed < 0 else 2 * RATE, preserve_pitch=False, rate=speed)
    rows = run_blocks(engine)
    assert max(m for m, _ in rows) <= 2
    # On average one mix per block, give or take the resampler's queue.
    assert sum(m for m, _ in rows) <= BLOCKS * 1.1


def test_reverse_5x_block_time_stays_near_its_median(rig, monkeypatch):
    """Self-relative: the same machine, the same run. Before the fix the
    p99 was 20 to 90 times the median; the budget here is 12 times plus 3 ms."""
    engine = build(Clock())
    engine._counter = Counter(monkeypatch)
    engine.play(110 * RATE, preserve_pitch=False, rate=-5.0)
    run_blocks(engine, 60)  # warm up
    times = np.array([ms for _, ms in run_blocks(engine)])
    assert np.percentile(times, 99) <= 12 * np.median(times) + 3.0
