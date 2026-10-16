"""Solo overrides mute, and solo is exclusive by default (WP24.1)."""

import numpy as np
import pytest

from kuulas import mixer, ops
from kuulas.model import Media, Project

RATE = 1000
#: Centred mono at full level, under the power pan law (stems.pan_gains).
ONE_TRACK = np.sqrt(0.5)


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


def two_tracks():
    """Tracks ``t`` and ``u``, each one clip of full-level mono."""
    frames = 2 * RATE
    store = MemoryStore({"m1": np.ones((1, frames), np.float32),
                         "m2": np.ones((1, frames), np.float32)})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m1", name="a.wav", channels=1, frames=frames))
    p = ops.add_media(p, Media(id="m2", name="b.wav", channels=1, frames=frames))
    p = ops.add_track(p, track_id="t", name="T")
    p = ops.add_track(p, track_id="u", name="U")
    p = ops.add_clip(p, track_id="t", media_id="m1", clip_id="ct")
    p = ops.add_clip(p, track_id="u", media_id="m2", clip_id="cu")
    return p, store


def level(p, store):
    return float(mixer.mix(p, store, 0, 1)[0, 0])


def test_solo_overrides_mute():
    p, store = two_tracks()
    p = ops.set_track(p, "t", mute=True, solo=True)
    # Only t is heard: it is soloed even though it is muted, and u is not soloed.
    assert level(p, store) == pytest.approx(ONE_TRACK, rel=1e-6)


def test_solo_is_exclusive_by_default():
    p, _ = two_tracks()
    p = ops.solo(p, "t")
    assert (p.track("t").solo, p.track("u").solo) == (True, False)
    p = ops.solo(p, "u")
    assert (p.track("t").solo, p.track("u").solo) == (False, True)


def test_additive_solo_keeps_the_others():
    p, _ = two_tracks()
    p = ops.solo(p, "t")
    p = ops.solo(p, "u", exclusive=False)
    assert (p.track("t").solo, p.track("u").solo) == (True, True)
    p = ops.solo(p, "t", exclusive=False)
    assert (p.track("t").solo, p.track("u").solo) == (False, True)


def test_resoloing_the_only_solo_clears_it():
    p, store = two_tracks()
    p = ops.solo(p, "t")
    p = ops.solo(p, "t")
    assert not any(t.solo for t in p.tracks)
    # With nothing soloed, mute is back in charge.
    assert level(p, store) == pytest.approx(2 * ONE_TRACK, rel=1e-6)


def test_muted_bus_stays_silent_under_solo():
    p, store = two_tracks()
    p = ops.add_bus(p, bus_id="b", name="B")
    p = ops.set_track(p, "t", bus="b")
    p = ops.set_bus(p, "b", mute=True)
    p = ops.solo(p, "t")
    # t is soloed but its bus is a deliberate send cut; u is not soloed.
    assert level(p, store) == 0.0
