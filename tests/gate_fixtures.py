"""Shared fixtures for the Auto-Silence gate tests (WP44): a synthetic
conversation, a heard-silence helper. Not a test module."""

import numpy as np

from kuulas import ops
from kuulas.model import Media, Project

RATE = 8000


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


def speech(rng, frames):
    """Noise with a 4 Hz syllable envelope: loud enough to count as talk."""
    t = np.arange(frames) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(frames)).astype(np.float32)


def conversation(seconds=300, voices=4, seed=5, bleed=0.5, turn=(0.2, 0.8)):
    """Four mics in one room: turns of ``turn`` seconds with breaths inside
    them, backchannels from the others, and every mic hearing the others at
    ``bleed`` of their level. Returns ``(project, store)``; tracks ``T0``...,
    one whole clip each."""
    rng = np.random.default_rng(seed)
    n = seconds * RATE
    clean = [np.zeros(n, dtype=np.float32) for _ in range(voices)]
    t = 0.0
    while t < seconds - 8:
        v = int(rng.integers(voices))
        dur = rng.uniform(*turn)
        pos, stop = int(t * RATE), int(min(seconds, t + dur) * RATE)
        while pos < stop:
            end = min(stop, pos + int(rng.uniform(0.15, 0.9) * RATE))
            clean[v][pos:end] = speech(rng, end - pos)
            pos = end + int(rng.uniform(0.05, 0.5) * RATE)
        if rng.random() < 0.5:
            w = (v + 1 + int(rng.integers(voices - 1))) % voices
            a = int((t + rng.uniform(0, dur)) * RATE)
            b = min(n, a + int(rng.uniform(0.15, 0.6) * RATE))
            clean[w][a:b] = 0.5 * speech(rng, b - a)
        t += dur * rng.uniform(0.5, 1.0)
    store = MemoryStore({
        f"m{i}": (clean[i] + sum(bleed * clean[j] for j in range(voices) if j != i)
                  + 0.0003 * rng.standard_normal(n).astype(np.float32))[None, :]
        for i in range(voices)})
    p = Project(rate=RATE)
    for i in range(voices):
        p = ops.add_media(p, Media(id=f"m{i}", name=f"{i}.wav", channels=1, frames=n))
        p = ops.add_track(p, track_id=f"T{i}", name=f"Voice {i}")
        p = ops.add_clip(p, track_id=f"T{i}", media_id=f"m{i}", clip_id=f"c{i}")
    return p, store
