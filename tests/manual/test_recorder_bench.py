"""Callback timing of the recorder's capture engine, with a fake device.

Not part of the default run (``norecursedirs``). Run by hand:

    uv run pytest -q -s tests/manual/test_recorder_bench.py

A thread plays the audio driver: every 1024 frames (21.3 ms at 48 kHz) it
calls the capture callback, exactly as PortAudio's callback thread would,
while the writer thread converts, writes and fsyncs real files (F_FULLFSYNC
on macOS). It prints, per run:

- lateness: how long after its due time the callback started. In Python the
  callback must take the GIL first, so this is what the writer thread costs
  the audio thread.
- duration: how long the callback itself ran (copy into the ring, counters).
- worst: lateness + duration, against the 21.3 ms block period; CoreAudio's
  buffer at ``latency="high"`` gives more slack than one block.

Writes up to ~100 MB under pytest's tmp folder for the 8-channel run.
"""

import sys
import threading
import time

import numpy as np
import pytest

from kuulas_recorder.capture import Capture
from kuulas_recorder.sources import counter_block

RATE = 48000
BLOCK = 1024


class TimedSource:
    def __init__(self, channels):
        self.channels = channels
        self.cb = None
        self.stop_flag = threading.Event()

    def describe(self):
        return {"name": "bench"}

    def start(self, on_block, _on_lost):
        self.cb = on_block

    def stop(self):
        self.stop_flag.set()

    def run(self, seconds):
        block = counter_block(0, BLOCK, self.channels)
        period = BLOCK / RATE
        n = int(seconds / period)
        late = np.zeros(n)
        dur = np.zeros(n)
        t0 = time.perf_counter()
        for i in range(n):
            due = t0 + i * period
            while (now := time.perf_counter()) < due:
                time.sleep(min(0.002, due - now))
            start = time.perf_counter()
            self.cb(block, BLOCK, False)
            end = time.perf_counter()
            late[i] = start - due
            dur[i] = end - start
        return late, dur


def ms(a, q):
    return np.percentile(a, q) * 1000


@pytest.mark.parametrize(("channels", "switch_ms"), [(1, 5.0), (8, 5.0), (8, 1.0)])
def test_callback_timing(tmp_path, channels, switch_ms):
    old = sys.getswitchinterval()
    sys.setswitchinterval(switch_ms / 1000)
    try:
        src = TimedSource(channels)
        events = []
        cap = Capture(src, folder=tmp_path, take=f"b{channels}", rate=RATE,
                      channels=list(range(1, channels + 1)),
                      names=[f"c{i}" for i in range(channels)], report=events.append,
                      blocksize=BLOCK)
        cap.start()
        late, dur = src.run(10.0)
        cap.stop()
    finally:
        sys.setswitchinterval(old)
    worst = late + dur
    period = BLOCK / RATE * 1000
    print(f"\n{channels} ch, switch interval {switch_ms} ms, {len(late)} callbacks:"
          f"\n  lateness p50 {ms(late, 50):.3f} p99 {ms(late, 99):.3f} "
          f"max {ms(late, 100):.3f} ms"
          f"\n  duration p50 {ms(dur, 50):.4f} p99 {ms(dur, 99):.4f} "
          f"max {ms(dur, 100):.3f} ms"
          f"\n  worst {ms(worst, 100):.3f} ms of a {period:.1f} ms block; "
          f"dropped {cap.ring.dropped_frames} frames; "
          f"flushes {sum(e['ev'] == 'flushed' for e in events)}")
    assert cap.ring.dropped_frames == 0


def test_baseline_without_a_writer():
    """The emulated driver thread alone: its own wake-up lateness."""
    src = TimedSource(1)
    src.start(lambda *_: None, None)
    late, _ = src.run(5.0)
    print(f"\nbaseline lateness p50 {ms(late, 50):.3f} p99 {ms(late, 99):.3f} "
          f"max {ms(late, 100):.3f} ms")


@pytest.mark.parametrize("switch_ms", [5.0, 1.0])
def test_with_a_busy_python_thread(tmp_path, switch_ms):
    """The worst case for Python: another thread that never sleeps holds the GIL
    until the switch interval forces it to let go. The worker has no such
    thread; this shows what one would cost."""
    old = sys.getswitchinterval()
    sys.setswitchinterval(switch_ms / 1000)
    stop = threading.Event()

    def spin():
        x = 0
        while not stop.is_set():
            x += 1

    t = threading.Thread(target=spin, daemon=True)
    t.start()
    try:
        src = TimedSource(1)
        cap = Capture(src, folder=tmp_path, take="busy", rate=RATE, channels=[1],
                      names=["c"], report=lambda e: None, blocksize=BLOCK)
        cap.start()
        late, _ = src.run(5.0)
        cap.stop()
    finally:
        stop.set()
        sys.setswitchinterval(old)
    print(f"\nbusy thread, switch {switch_ms} ms: lateness p50 {ms(late, 50):.3f} "
          f"p99 {ms(late, 99):.3f} max {ms(late, 100):.3f} ms; "
          f"dropped {cap.ring.dropped_frames}")
