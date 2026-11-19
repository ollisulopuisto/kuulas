"""Hardware smoke test: one second of a sine through the default output.

Not part of the default run (``norecursedirs`` in pyproject.toml). Run it
by hand on a Mac and on Windows, with the volume down:

    uv run pytest -q tests/hardware/test_play.py -s

It should play a quiet 440 Hz tone for one second, cleanly.
"""

import threading
import time

import numpy as np
import sounddevice as sd

from kuulas import ops
from kuulas.engine import Engine
from kuulas.model import Media, Project

RATE = 48000


class MemoryStore:
    def __init__(self, audio: np.ndarray):
        self.audio = audio

    def read(self, _media_id: str, first: int, count: int) -> np.ndarray:
        out = np.zeros((1, count), dtype=np.float32)
        lo, hi = max(0, first), min(self.audio.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = self.audio[:, lo:hi]
        return out


class OneClip:
    def __init__(self):
        t = np.arange(RATE) / RATE
        audio = (0.1 * np.sin(2 * np.pi * 440 * t))[None, :].astype(np.float32)
        p = Project(rate=RATE)
        p = ops.add_media(p, Media(id="sine", name="sine.wav", channels=1, frames=RATE))
        p = ops.add_track(p, "t", "Sine")
        self.state = ops.add_clip(p, "t", "sine")
        self.store = MemoryStore(audio)
        self.lock = threading.RLock()

    def subscribe(self, _fn):
        pass


def test_one_second_of_sine_plays_on_the_default_device():
    print("\noutput:", sd.query_devices(kind="output")["name"])
    engine = Engine(OneClip())
    try:
        engine.play(0)
        started = time.monotonic()
        positions = []
        while engine.status()["playing"] and time.monotonic() - started < 5:
            positions.append(engine.status()["position"])
            time.sleep(0.05)
        elapsed = time.monotonic() - started
        status = engine.status()
        print("status:", {k: v for k, v in status.items() if k != "notices"})
        for notice in status["notices"]:
            print("notice:", notice["text"])
    finally:
        engine.close()
    assert not status["playing"], "playback did not finish within 5 s"
    assert status["position"] == RATE
    assert status["failed_blocks"] == 0
    assert 0.9 < elapsed < 2.0, f"one second took {elapsed:.2f} s"
    assert positions == sorted(positions), "the playhead went backwards"
    # Display follows the ear: shortly after play, the heard position trails
    # the start by the device latency, so the first samples read near 0.
    assert positions[0] < RATE // 10
