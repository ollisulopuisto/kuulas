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


# -- the gate (WP44) ---------------------------------------------------------

GATE_RAMP = round(mixer.GATE_RAMP_SEC * RATE)  # 30 frames at this rate


def gated(ranges, seconds=2):
    p, store = setup(seconds)
    return ops.set_gate(p, "t", ranges), store


def stem(p, store, first, count):
    return mixer.track_stem(p.track("t"), store, first, count, 1, as_heard=False,
                            rate=RATE)[0]


def test_the_gate_ramp_is_thirty_milliseconds():
    assert mixer.GATE_RAMP_SEC == 0.030
    assert GATE_RAMP == 30


def test_a_gated_stretch_is_silent_and_the_rest_untouched():
    p, store = gated([(800, 1200)])
    s = stem(p, store, 0, 2000)
    assert not s[800:1200].any()
    assert (s[:800 - GATE_RAMP] == 1.0).all()
    assert (s[1200 + GATE_RAMP:] == 1.0).all()


def test_the_edges_ramp_down_before_and_up_after_the_gate():
    p, store = gated([(800, 1200)])
    s = stem(p, store, 0, 2000)
    assert np.all(np.diff(s[800 - GATE_RAMP:800]) <= 0)
    assert np.all(np.diff(s[1200:1200 + GATE_RAMP]) >= 0)
    assert 0.0 < s[800 - GATE_RAMP + 1] < 1.0
    assert 0.0 < s[1200 + 1] < 1.0
    assert s[799] == 0.0
    assert s[1200] == 0.0


def test_mix_and_stem_agree_on_the_gate():
    p, store = gated([(800, 1200), (1500, 1700)])
    whole = mixer.mix(p, store, 0, 2000)[0] / np.sqrt(0.5)
    np.testing.assert_allclose(whole, stem(p, store, 0, 2000), atol=1e-6)


def test_chunked_rendering_equals_one_render():
    p, store = gated([(800, 1200), (1500, 1700)])
    whole = mixer.mix(p, store, 0, 2000)
    parts = np.concatenate([mixer.mix(p, store, a, 137) for a in range(0, 2000, 137)],
                           axis=1)[:, :2000]
    np.testing.assert_allclose(parts, whole, atol=1e-7)


def test_a_block_that_only_sees_the_ramp_still_gets_it():
    p, store = gated([(800, 1200)])
    s = stem(p, store, 800 - GATE_RAMP // 2, 10)
    assert (s < 1.0).all()
    assert (s > 0.0).all()


def test_the_ramp_is_applied_once_when_clips_overlap():
    # Two clips crossfading under one gate edge would get a gate ramp each
    # if the gate were applied per clip; it is applied to the track sum.
    p, store = setup()
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="d")
    p = ops.set_gate(p, "t", [(800, 1200)])
    ref, _ = setup()
    ref = ops.set_gate(ref, "t", [(800, 1200)])
    two = stem(p, store, 0, 2000)
    one = stem(ref, store, 0, 2000)
    np.testing.assert_allclose(two, 2 * one, atol=1e-6)


def test_a_gate_edge_on_a_clip_edge_is_not_ramped_twice():
    p, store = setup()
    p = ops.split_clip(p, "c", at=1200, new_id="c2")
    p = ops.set_gate(p, "t", [(800, 1200)])
    split = stem(p, store, 0, 2000)
    whole = stem(*gated([(800, 1200)]), 0, 2000)
    np.testing.assert_allclose(split, whole, atol=1e-6)


def test_gate_matches_the_old_clip_piece_result_within_the_ramp():
    ranges = [(500, 900), (1300, 1500)]
    old, store = setup()
    old = ops.mute_ranges(old, "t", ranges)
    new, _ = gated(ranges)
    a = stem(old, store, 0, 2000)
    b = stem(new, store, 0, 2000)
    # Same silence, same ramp length; the pieces ramp with the same raised sine.
    assert np.array_equal(a == 0.0, b == 0.0)
    np.testing.assert_allclose(a, b, atol=1e-6)


def test_gate_with_nothing_in_the_block_costs_no_change():
    p, store = gated([(1800, 1900)])
    s = stem(p, store, 0, 100)
    assert (s == 1.0).all()


def test_gate_applies_before_track_gain_and_bus():
    p, store = gated([(800, 1200)])
    p = ops.set_track(p, "t", gain_db=-6.0)
    out = mixer.mix(p, store, 900, 100)
    assert not out.any()


def test_mix_of_a_gated_track_equals_the_old_clip_piece_mix():
    ranges = [(500, 900), (1300, 1500)]
    old, store = setup(channels=2)
    old = ops.mute_ranges(old, "t", ranges)
    new, _ = setup(channels=2)
    new = ops.set_gate(new, "t", ranges)
    np.testing.assert_allclose(mixer.mix(new, store, 0, 2000),
                               mixer.mix(old, store, 0, 2000), atol=1e-6)
