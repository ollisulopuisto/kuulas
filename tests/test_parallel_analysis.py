"""Speech lanes are measured one track per core (WP14)."""

import threading

import numpy as np

from kuulas import analysis, ops
from kuulas.model import Media, Project

RATE = 8000
SEC = 6


class MemoryStore:
    def __init__(self, arrays):
        self.arrays = arrays

    def read(self, media_id, first, count):
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


def three_speakers():
    rng = np.random.default_rng(3)
    n = SEC * RATE
    store = MemoryStore({f"m{i}": rng.standard_normal((1, n)).astype(np.float32) * 0.2
                         for i in range(3)})
    p = Project(rate=RATE)
    for i in range(3):
        p = ops.add_media(p, Media(id=f"m{i}", name=f"s{i}.wav", channels=1, frames=n))
        p = ops.add_track(p, track_id=f"T{i}", name=f"Speaker {i}")
        p = ops.add_clip(p, track_id=f"T{i}", media_id=f"m{i}", clip_id=f"c{i}")
    return p, store


def test_parallel_and_serial_lanes_are_identical(monkeypatch):
    p, store = three_speakers()
    monkeypatch.setattr(analysis, "workers", lambda: 1)
    serial = analysis.speech_lanes(p, store).speakers
    monkeypatch.setattr(analysis, "workers", lambda: 4)
    parallel = analysis.speech_lanes(p, store).speakers
    assert [lane.name for lane in parallel] == [lane.name for lane in serial]
    for a, b in zip(serial, parallel, strict=True):
        assert np.array_equal(a.on, b.on)
        assert np.array_equal(a.level, b.level)


def test_speech_tracks_are_measured_at_the_same_time(monkeypatch):
    # Each measurement waits at a barrier for the others. Serial code never
    # gets all three there, so the barrier breaks; parallel code passes it.
    p, store = three_speakers()
    barrier = threading.Barrier(3, timeout=2)
    real = analysis.track_levels

    def meet_then_measure(project, src, track):
        barrier.wait()
        return real(project, src, track)

    monkeypatch.setattr(analysis, "track_levels", meet_then_measure)
    monkeypatch.setattr(analysis, "workers", lambda: 4)
    analysis.speech_lanes(p, store)
