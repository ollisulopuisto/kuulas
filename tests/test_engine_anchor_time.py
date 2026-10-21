"""The time an anchor says its position was heard at (owner, 2026-10-21: "stutter in
playback cursor's location again! jumps a few pixels back and then keeps continuing").

The callback reads the monotonic clock when Python gets to run it. A callback that
waited for the GIL runs late, its position is the one the device asked for, and an
anchor dated by the late clock reads says the position was heard later than it was:
the browser's cursor then lands behind by the wait. PortAudio's own ``currentTime`` is
taken in the host thread before Python runs, so the engine dates an anchor with it
(mapped onto the clock by the least delayed recent callback). No audio device here."""

from types import SimpleNamespace

import numpy as np
import pytest
from test_engine import RATE, Clock, install_rig, make, noise

BLOCK = 1024
STEP = BLOCK / RATE


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


def run(engine, clock, delays, stream_start=500.0):
    """Callbacks that PortAudio makes every block; Python starts each ``delay`` late.
    Returns (position, t) as the status reports them after each."""
    t0 = clock.now
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    seen = []
    for k, delay in enumerate(delays):
        due = t0 + (k + 1) * STEP
        clock.now = due + delay
        info = SimpleNamespace(currentTime=stream_start + (k + 1) * STEP,
                               outputBufferDacTime=stream_start + (k + 1) * STEP + 0.03)
        engine._callback(out, BLOCK, info, SimpleNamespace(output_underflow=False))
        status = engine.status()
        seen.append((status["position"], status["t"]))
    return seen


def test_a_callback_that_ran_late_does_not_make_the_anchor_late(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(10)})
    engine.play(0)
    delays = [0.0, 0.0, 0.0, 0.0, 0.0, 0.08, 0.0, 0.0, 0.05, 0.0, 0.0, 0.0]
    seen = run(engine, clock, delays)
    # position/rate - t is the same for every anchor of a steady run
    offsets = [position / RATE - t for position, t in seen[2:]]
    assert max(offsets) - min(offsets) < 0.002, offsets


def test_without_time_info_the_clock_is_used_as_before(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(10)})
    engine.play(0)
    clock.now += 0.5
    engine._callback(np.zeros((BLOCK, 2), dtype=np.float32), BLOCK, None,
                     SimpleNamespace(output_underflow=False))
    assert engine.status()["t"] == clock.now


def test_a_currenttime_that_stands_still_is_not_trusted(rig, clock):
    engine, _, _ = make(rig, clock, {"m": noise(10)})
    engine.play(0)
    out = np.zeros((BLOCK, 2), dtype=np.float32)
    info = SimpleNamespace(currentTime=500.0, outputBufferDacTime=500.03)
    for _ in range(10):
        clock.now += STEP
        engine._callback(out, BLOCK, info, SimpleNamespace(output_underflow=False))
    assert engine.status()["t"] == clock.now
