import numpy as np
import pyloudnorm
import pytest

from kuulas import mixer, ops
from kuulas.model import Media, Project

RATE = 1000  # small rate keeps the arrays readable


class MemoryStore:
    def __init__(self, arrays: dict[str, np.ndarray]):
        self.arrays = arrays

    def read(self, media_id: str, first: int, count: int) -> np.ndarray:
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        piece = a[:, max(0, first):first + count]
        out[:, : piece.shape[1]] = piece
        return out


def setup(seconds=2, channels=1):
    frames = seconds * RATE
    store = MemoryStore({"m": np.ones((channels, frames), dtype=np.float32)})
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=channels, frames=frames))
    p = ops.add_track(p, track_id="t", name="T")
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c")
    return p, store


def test_centred_mono_clip_uses_the_power_law():
    p, store = setup()
    out = mixer.mix(p, store, 0, 10)
    np.testing.assert_allclose(out[:, 0], [np.sqrt(0.5)] * 2, rtol=1e-6)


def test_clip_gain_and_envelope_in_source_time():
    p, store = setup()
    p = ops.set_clip(p, "c", gain_db=-6.0)
    p = ops.set_clip_envelope(p, "c", [(0, 0.0), (1000, -6.0)])
    p = ops.trim_clip(p, "c", start=500)  # clip now starts at source frame 500
    out = mixer.mix(p, store, 500, 1)
    expected = np.sqrt(0.5) * 10 ** ((-6.0 - 3.0) / 20)
    assert out[0, 0] == pytest.approx(expected, rel=1e-5)


def test_mute_and_solo():
    p, store = setup()
    p = ops.add_track(p, track_id="u", name="U")
    p = ops.add_clip(p, track_id="u", media_id="m", clip_id="d")
    both = mixer.mix(p, store, 0, 1)[0, 0]
    solo = mixer.mix(ops.set_track(p, "u", solo=True), store, 0, 1)[0, 0]
    mute = mixer.mix(ops.set_track(p, "t", mute=True), store, 0, 1)[0, 0]
    assert solo == pytest.approx(both / 2)
    assert mute == pytest.approx(both / 2)


def test_bus_gain_applies_only_to_its_tracks():
    p, store = setup()
    p = ops.add_bus(p, bus_id="b", name="B")
    p = ops.set_track(p, "t", bus="b")
    p = ops.set_bus(p, "b", gain_db=-120.0)
    assert abs(mixer.mix(p, store, 0, 1)[0, 0]) < 1e-5


def test_track_automation_is_timeline_time():
    p, store = setup()
    p = ops.set_track_automation(p, "t", [(0, -6.0)])
    out = mixer.mix(p, store, 100, 1)
    assert out[0, 0] == pytest.approx(np.sqrt(0.5) * 10 ** (-6 / 20), rel=1e-5)


def test_fades_start_silent_and_end_full():
    p, store = setup()
    p = ops.set_clip(p, "c", fade_in=100)
    out = mixer.mix(p, store, 0, 101)
    assert out[0, 0] == 0.0
    assert out[0, 100] == pytest.approx(np.sqrt(0.5))


def test_blocks_join_seamlessly():
    p, store = setup()
    p = ops.set_clip(p, "c", fade_in=300, fade_out=300)
    p = ops.set_clip_envelope(p, "c", [(0, 0.0), (2000, -20.0)])
    whole = mixer.mix(p, store, 0, 2000)
    pieces = np.concatenate([mixer.mix(p, store, f, 128) for f in range(0, 2000, 128)],
                            axis=1)[:, :2000]
    np.testing.assert_allclose(whole, pieces, atol=1e-6)


def test_crossfade_keeps_constant_gain_across_the_join():
    p, store = setup()
    p = ops.ripple_delete(p, 500, 1000)
    a, b = p.track("t").clips
    assert a.xfade_out
    assert b.xfade_in
    out = mixer.mix(p, store, 400, 200)
    np.testing.assert_allclose(out[0], np.sqrt(0.5), rtol=1e-6)


def test_crossfade_plays_the_audio_beyond_the_cut():
    # Distinct source values on each side make the crossfade audible.
    p, _ = setup()
    ramp = np.arange(2000, dtype=np.float32)[None, :]
    store = MemoryStore({"m": ramp})
    p = ops.ripple_delete(p, 500, 1000)
    a, _ = p.track("t").clips
    half = a.xfade_out // 2
    out = mixer.mix(p, store, 500 - half, a.xfade_out)[0] / np.sqrt(0.5)
    # At the start of the crossfade we hear the left clip's own audio...
    assert out[0] == pytest.approx(500 - half, rel=1e-3)
    # ...and at its end, the right clip's (source 1000 + half - 1).
    assert out[-1] == pytest.approx(1000 + half - 1, rel=1e-2)


def test_hard_panned_mono_is_silent_on_the_other_side():
    p, store = setup()
    p = ops.set_clip(p, "c", pan=-1.0)
    out = mixer.mix(p, store, 0, 1)
    assert out[1, 0] == pytest.approx(0.0, abs=1e-7)
    assert out[0, 0] == pytest.approx(1.0)


def test_silence_after_the_last_clip():
    p, store = setup()
    assert not mixer.mix(p, store, 5000, 10).any()


def test_stereo_source_keeps_its_channels_apart():
    p, _ = setup(channels=2)
    audio = np.stack([np.ones(2 * RATE), -np.ones(2 * RATE)]).astype(np.float32)
    store = MemoryStore({"m": audio})
    out = mixer.mix(p, store, 0, 1)
    assert (out[0, 0], out[1, 0]) == (1.0, -1.0)


def test_centred_mono_voice_measures_the_same_loudness_as_alone():
    rate = 48000
    rng = np.random.default_rng(0)
    voice = (0.1 * rng.standard_normal(3 * rate)).astype(np.float32)
    p = Project(rate=rate)
    p = ops.add_media(p, Media(id="m", name="v.wav", channels=1, frames=voice.size))
    p = ops.add_track(p, track_id="t", name="T")
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c")
    out = mixer.mix(p, MemoryStore({"m": voice[None, :]}), 0, voice.size)
    meter = pyloudnorm.Meter(rate)
    alone = meter.integrated_loudness(voice.astype(np.float64))
    mixed = meter.integrated_loudness(out.T.astype(np.float64))
    assert mixed == pytest.approx(alone, abs=0.1)
