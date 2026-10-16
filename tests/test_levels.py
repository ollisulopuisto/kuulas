"""Level envelopes per media (WP36): an edit re-reads no audio.

``analysis.track_levels`` used to read every source again after each edit.
Now it composes the timeline from one cached envelope per media. The result
must equal the audio path's, which stays as the fallback.
"""

import numpy as np
import pytest
import soundfile as sf

from kuulas import analysis, levels, ops
from kuulas.media import MediaStore
from kuulas.memory import MemoryBudget
from kuulas.model import Media, Project

RATE = 8000
SEC = 12


class AudioOnly:
    """A store with nothing but ``read``: the audio path, i.e. today's result."""

    def __init__(self, arrays):
        self.arrays = arrays
        self.reads = 0

    def read(self, media_id, first, count):
        self.reads += 1
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


class WithEnvelopes(AudioOnly):
    """The same audio, plus a per-media envelope computed once."""

    def __init__(self, arrays):
        super().__init__(arrays)
        self.made = {}

    def envelope(self, media_id, block):
        if (media_id, block) not in self.made:
            frames = self.arrays[media_id].shape[1]
            self.made[media_id, block] = levels.block_energy(
                lambda a, n, m=media_id: self.read(m, a, n), frames, block)
        return self.made[media_id, block]


def speech(rng, seconds):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(n)).astype(np.float32)


@pytest.fixture
def room():
    rng = np.random.default_rng(1)
    n = SEC * RATE
    a = np.zeros(n, dtype=np.float32)
    v = np.zeros(n, dtype=np.float32)
    a[: 4 * RATE] = speech(rng, 4)
    v[6 * RATE: 10 * RATE] = speech(rng, 4)
    floor = lambda: 0.0003 * rng.standard_normal(n).astype(np.float32)  # noqa: E731
    arrays = {"a": (a + 0.1 * v + floor())[None, :],
              "v": (v + 0.1 * a + floor())[None, :],
              "s": np.stack([a, v])}  # stereo
    p = Project(rate=RATE)
    for mid, ch in (("a", 1), ("v", 1), ("s", 2)):
        p = ops.add_media(p, Media(id=mid, name=f"{mid}.wav", channels=ch, frames=n))
    p = ops.add_track(p, track_id="A", name="Anna")
    p = ops.add_track(p, track_id="V", name="Ville")
    p = ops.add_clip(p, track_id="A", media_id="a", clip_id="ca")
    p = ops.add_clip(p, track_id="V", media_id="v", clip_id="cv")
    return p, arrays


def both(p, arrays, track_id):
    track = p.track(track_id)
    want = analysis.track_levels(p, AudioOnly(arrays), track)
    fast = WithEnvelopes(arrays)
    got = analysis.track_levels(p, fast, track)
    return want, got, fast


def same(want, got):
    np.testing.assert_allclose(got[0], want[0], atol=1e-3)
    np.testing.assert_array_equal(got[1], want[1])


def test_envelope_composition_equals_the_audio_path(room):
    p, arrays = room
    for tid in ("A", "V"):
        want, got, fast = both(p, arrays, tid)
        same(want, got)
        assert fast.reads > 0  # the envelope itself was made from audio, once


def test_stereo_is_averaged_to_mono_as_before(room):
    p, arrays = room
    p = ops.add_track(p, track_id="S", name="Music", kind="speech")
    p = ops.add_clip(p, track_id="S", media_id="s", clip_id="cs")
    same(*both(p, arrays, "S")[:2])


def test_a_trimmed_moved_and_split_clip_equals_the_audio_path(room):
    p, arrays = room
    block = levels.block_frames(analysis.hop_frames(RATE))
    # split and cut at multiples of the block, but mid-hop
    p = ops.split_clip(p, "ca", at=5 * RATE + 7 * block)
    p = ops.ripple_delete(p, 2 * RATE + 11 * block, 3 * RATE + 11 * block)
    same(*both(p, arrays, "A")[:2])


def test_edits_off_the_block_grid_stay_within_a_hair(room):
    """A cut at an arbitrary frame shifts the later piece off the envelope's
    block grid; the block is split in proportion. Only a hop whose energy is
    all in one edge block (the gated noise's hard on/off edges) is off by
    more than a fraction of a dB; a decision edge moves by at most one hop."""
    p, arrays = room
    p = ops.ripple_delete(p, 1 * RATE + 3, 2 * RATE + 5)
    want, got, _ = both(p, arrays, "V")
    err = np.abs(got[0] - want[0])
    assert np.percentile(err, 95) < 0.5
    np.testing.assert_array_equal(got[1], want[1])
    hop = analysis.hop_frames(RATE)
    fast = analysis.silence_ranges(p, WithEnvelopes(arrays))
    slow = analysis.silence_ranges(p, AudioOnly(arrays))
    assert fast.keys() == slow.keys()
    for tid, ranges in slow.items():
        assert len(fast[tid]) == len(ranges)
        for (a, b), (c, d) in zip(fast[tid], ranges, strict=True):
            assert abs(a - c) <= hop
            assert abs(b - d) <= hop


def test_an_edit_causes_no_audio_reads(room):
    p, arrays = room
    store = WithEnvelopes(arrays)
    for t in p.tracks:
        analysis.track_levels(p, store, t)  # warms the envelopes
    store.reads = 0
    edited = ops.ripple_delete(p, 3 * RATE, 4 * RATE)
    inside = next(c for c in edited.track("V").clips if c.start < 5 * RATE < c.end)
    edited = ops.split_clip(edited, inside.id, at=5 * RATE)
    for t in edited.tracks:
        analysis.track_levels(edited, store, t)
    assert store.reads == 0


def test_overlapping_clips_on_a_track_fall_back_to_the_audio(room):
    """Overlap sums the waveforms before squaring: no envelope can do that."""
    p, arrays = room
    p = ops.add_clip(p, track_id="A", media_id="v", clip_id="over", start=5 * RATE)
    want, got, _ = both(p, arrays, "A")
    same(want, got)


def test_a_store_without_envelopes_is_still_served(room):
    p, arrays = room
    got = analysis.track_levels(p, AudioOnly(arrays), p.track("A"))
    assert got[0].dtype == np.float32


def test_speech_lanes_decisions_are_unchanged(room):
    p, arrays = room
    plain = analysis.silence_ranges(p, AudioOnly(arrays))
    fast = analysis.silence_ranges(p, WithEnvelopes(arrays))
    assert plain == fast


def test_block_divides_the_hop():
    for rate in (8000, 22050, 44100, 48000, 96000):
        hop = analysis.hop_frames(rate)
        block = levels.block_frames(hop)
        assert hop % block == 0
        assert 1 <= block <= max(1, hop // 16)


def test_real_store_envelope_is_cached_on_disk_keyed_by_content(tmp_path):
    rng = np.random.default_rng(3)
    src = tmp_path / "a.wav"
    sf.write(src, (rng.standard_normal(48000 * 3) * 0.1).astype(np.float32), 48000,
             subtype="PCM_16")
    store = MediaStore(tmp_path / "media", rate=48000, budget=MemoryBudget())
    media = store.import_file(src)
    block = levels.block_frames(analysis.hop_frames(48000))
    env = store.envelope(media.id, block)
    assert env is not None
    audio = store.read(media.id, 0, media.frames)[0].astype(np.float64)
    assert env.sum() == pytest.approx(float(np.square(audio).sum()), rel=1e-9)
    assert any((tmp_path / "caches" / "analysis").glob("*.npy"))
    # a new process: nothing in memory, the file answers, no audio is read
    class NoAudio(MediaStore):
        def read(self, *a, **k):
            raise AssertionError("audio was read")

    fresh = NoAudio(tmp_path / "media", rate=48000, budget=MemoryBudget())
    np.testing.assert_array_equal(fresh.envelope(media.id, block), env)


def test_real_store_edit_reads_no_audio_and_equals_the_audio_path(tmp_path):
    rng = np.random.default_rng(4)
    src = tmp_path / "a.wav"
    data = (rng.standard_normal(48000 * 5) * 0.1).astype(np.float32)
    data[48000:96000] *= 0.01
    sf.write(src, data, 48000, subtype="PCM_16")

    reads = []

    class Counting(MediaStore):
        def read(self, media_id, first, count):
            reads.append(count)
            return super().read(media_id, first, count)

    store = Counting(tmp_path / "media", rate=48000, budget=MemoryBudget())
    media = store.import_file(src)
    p = Project(rate=48000, media=(media,))
    p = ops.add_track(p, track_id="T", name="T")
    p = ops.add_clip(p, track_id="T", media_id=media.id, clip_id="c")
    analysis.track_levels(p, store, p.track("T"))
    reads.clear()
    p = ops.ripple_delete(p, 48000 * 2, 48000 * 3)  # whole-sample-block aligned
    got = analysis.track_levels(p, store, p.track("T"))
    assert reads == []
    want = analysis.track_levels(p, AudioOnly({media.id: store.read(
        media.id, 0, media.frames)}), p.track("T"))
    same(want, got)
