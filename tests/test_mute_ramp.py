"""Mute ramps are derived at mix time, never stored (so unmute is exact)."""

from dataclasses import replace

import numpy as np

from kuulas import mixer, ops
from kuulas.model import Media, Project

RATE = 1000
RAMP = round(mixer.GATE_RAMP_SEC * RATE)  # 30 frames


class MemoryStore:
    def __init__(self, arrays):
        self.arrays = arrays

    def read(self, media_id, first, count):
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        piece = a[:, max(0, first):first + count]
        out[:, : piece.shape[1]] = piece
        return out


def setup(channels=1):
    frames = 2 * RATE
    rng = np.random.default_rng(1)
    noise = rng.uniform(0.5, 1.0, (channels, frames)).astype(np.float32)
    store = MemoryStore({"m": noise, "o": np.ones((channels, frames), dtype=np.float32)})
    p = Project(rate=RATE)
    for m in ("m", "o"):
        media = Media(id=m, name=f"{m}.wav", channels=channels, frames=frames)
        p = ops.add_media(p, media)
    p = ops.add_track(p, track_id="t", name="T")
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c")
    return p, store


def stem(p, store, first=0, count=2000):
    return mixer.track_stem(p.track("t"), store, first, count, 1, as_heard=False,
                            rate=RATE)[0]


def muted_clip(p):
    return next(c for c in p.track("t").clips if c.muted)


def test_mute_then_unmute_restores_stored_fades_and_render_exactly():
    p, store = setup()
    p = ops.set_clip(p, "c", fade_in=10, fade_out=20)
    out_before = mixer.mix(p, store, 0, 2000)
    q = ops.mute_range(p, 800, 1200, ["t"])
    q = ops.set_clip(q, muted_clip(q).id, muted=False)
    got = [(c.start, c.length, c.fade_in, c.fade_out) for c in q.track("t").clips]
    assert [(s, ln) for s, ln, *_ in got] == [(0, 800), (800, 400), (1200, 800)]
    assert [g[2:] for g in got] == [(10, 0), (0, 0), (0, 20)]
    assert np.array_equal(mixer.mix(q, store, 0, 2000), out_before)


def test_mute_writes_no_fades():
    p, _ = setup()
    q = ops.mute_ranges(p, "t", [(500, 900)])
    assert all(c.fade_in == 0 and c.fade_out == 0 for c in q.track("t").clips)


def test_neighbours_ramp_to_zero_at_a_muted_edge():
    p, store = setup()
    s0 = stem(p, store)
    q = ops.mute_range(p, 800, 1200, ["t"])
    s = stem(q, store)
    assert not s[800:1200].any()
    assert s[799] == 0.0
    assert s[1200] == 0.0
    assert np.all(np.diff(s[800 - RAMP:800] / s0[800 - RAMP:800]) <= 0)
    assert np.all(np.diff(s[1200:1200 + RAMP] / s0[1200:1200 + RAMP]) >= 0)
    assert 0 < s[1201] < s0[1201]
    np.testing.assert_array_equal(s[:800 - RAMP], s0[:800 - RAMP])
    np.testing.assert_array_equal(s[1200 + RAMP:], s0[1200 + RAMP:])


def test_no_ramp_next_to_a_muted_piece_of_another_media_or_gap():
    p, store = setup()
    p = ops.split_clip(p, "c", 1000)
    right = next(c for c in p.track("t").clips if c.start == 1000)
    plain = stem(p, store)
    for other in (replace(right, media="o"), replace(right, offset=right.offset + 5)):
        tr = p.track("t")
        clips = tuple(replace(other, muted=True) if c.id == right.id else c
                      for c in tr.clips)
        r = ops._replace_track(p, replace(tr, clips=clips))
        np.testing.assert_array_equal(stem(r, store)[:1000], plain[:1000])
    # control: the same piece muted with contiguous source does ramp
    r = ops.set_clip(p, right.id, muted=True)
    assert stem(r, store)[999] == 0.0


def test_chunked_rendering_equals_one_block_for_any_block_size():
    p, store = setup(channels=2)
    p = ops.mute_range(p, 800, 1200, ["t"])
    p = ops.mute_range(p, 1500, 1530, ["t"])
    whole = mixer.mix(p, store, 0, 2000)
    for size in (1, 7, 30, 64, 333):
        parts = [mixer.mix(p, store, f, min(size, 2000 - f))
                 for f in range(0, 2000, size)]
        assert np.array_equal(np.concatenate(parts, axis=1), whole)


def test_mix_and_stem_agree():
    p, store = setup()
    p = ops.mute_range(p, 800, 1200, ["t"])
    whole = mixer.mix(p, store, 0, 2000)[0] / np.sqrt(0.5)
    np.testing.assert_allclose(whole, stem(p, store), atol=1e-6)


def test_projects_with_stored_mute_fades_render_as_before():
    p, store = setup()
    q = ops.mute_range(p, 800, 1200, ["t"])
    legacy = ops._replace_track(q, replace(q.track("t"), clips=tuple(
        replace(c, fade_out=RAMP) if c.end == 800 else
        replace(c, fade_in=RAMP) if c.start == 1200 else c for c in q.track("t").clips)))
    np.testing.assert_array_equal(stem(legacy, store), stem(q, store))


def test_crossfade_is_not_stored_next_to_a_muted_piece():
    p, _ = setup()
    p = ops.mute_range(p, 800, 1200, ["t"])
    p = ops.ripple_delete(p, 1000, 1500, ["t"])
    assert all(c.xfade_in == 0 and c.xfade_out == 0 for c in p.track("t").clips)
