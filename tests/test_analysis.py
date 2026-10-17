"""Auto-Silence and automix ducking, decided by speechmix's speech grid.

Two microphones in one room: each hears its owner loudly and the other
person as bleed 20 dB down, over a quiet noise floor.
"""

import numpy as np
import pytest

from kuulas import analysis, curves, ops
from kuulas.model import Media, Project

RATE = 8000
SEC = 12


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


def speech(rng, seconds):
    """Noise with a 4 Hz syllable envelope: loud enough to count as talk."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(n)).astype(np.float32)


@pytest.fixture
def room():
    rng = np.random.default_rng(1)
    n = SEC * RATE
    anna = np.zeros(n, dtype=np.float32)
    ville = np.zeros(n, dtype=np.float32)
    anna[: 4 * RATE] = speech(rng, 4)  # Anna talks 0-4 s
    ville[6 * RATE: 10 * RATE] = speech(rng, 4)  # Ville talks 6-10 s
    floor = lambda: 0.0003 * rng.standard_normal(n).astype(np.float32)  # noqa: E731
    mic_a = anna + 0.1 * ville + floor()
    mic_v = ville + 0.1 * anna + floor()
    store = MemoryStore({"a": mic_a[None, :], "v": mic_v[None, :]})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="a", name="a.wav", channels=1, frames=n))
    p = ops.add_media(p, Media(id="v", name="v.wav", channels=1, frames=n))
    p = ops.add_track(p, track_id="A", name="Anna")
    p = ops.add_track(p, track_id="V", name="Ville")
    p = ops.add_clip(p, track_id="A", media_id="a", clip_id="ca")
    p = ops.add_clip(p, track_id="V", media_id="v", clip_id="cv")
    return p, store


def covered(ranges, t, rate=RATE):
    return any(a <= t * rate < b for a, b in ranges)


def test_silence_ranges_close_each_mic_while_the_other_talks(room):
    p, store = room
    closed = analysis.silence_ranges(p, store)
    # Anna's mic is closed while only Ville talks, open while she does.
    assert covered(closed["A"], 8.0)
    assert not covered(closed["A"], 2.0)
    assert covered(closed["V"], 2.0)
    assert not covered(closed["V"], 8.0)


def test_auto_silence_gates_the_track_and_never_splits_clips(room):
    # WP44 replaced the clip pieces (owner decision 2026-10-18): same
    # closed stretches, stored as one merged gate per track.
    p, store = room
    q = analysis.auto_silence(p, store)
    assert q.track("A").clips == p.track("A").clips
    assert covered(q.track("A").gate, 8.0)
    assert not covered(q.track("A").gate, 2.0)
    assert q.track("A").gate == tuple(analysis.silence_ranges(p, store)["A"])


def test_automix_writes_ducking_as_editable_track_automation(room):
    p, store = room
    q = analysis.automix(p, store)
    auto = q.track("A").automation
    assert auto, "Anna's mic should duck under Ville"
    assert curves.value_at(auto, 8 * RATE) < -3.0
    assert curves.value_at(auto, 2 * RATE) == 0.0


def test_stereo_music_tracks_never_count_as_talkers(room):
    p, store = room
    rng = np.random.default_rng(2)
    n = SEC * RATE
    store.arrays["mus"] = (0.3 * rng.standard_normal((2, n))).astype(np.float32)
    p = ops.add_media(p, Media(id="mus", name="bed.wav", channels=2, frames=n))
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    p = ops.add_clip(p, track_id="M", media_id="mus", clip_id="cm")
    closed = analysis.silence_ranges(p, store)
    assert "M" not in closed
    # Loud music everywhere must not close the voices.
    assert not covered(closed["A"], 2.0)
    q = analysis.auto_silence(p, store)
    assert q.track("M") == p.track("M")
