"""Track effect layers, WP23a first slice: a causal high-pass with bypass. No device."""

import numpy as np
import pytest
from test_engine import RATE, Clock, MemoryStore, install_rig, make, noise, project_with

from kuulas import fx, mixer, ops
from kuulas.model import FxLayer, Project
from kuulas.ops import EditError


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


def tone(hz, seconds=1.0, rate=RATE):
    t = np.arange(round(seconds * rate)) / rate
    return (0.5 * np.sin(2 * np.pi * hz * t))[None, :].repeat(2, axis=0)


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


LAYER = FxLayer("highpass", 200.0, False)


def test_the_filter_cuts_below_the_cutoff_and_passes_above():
    low = fx.process_whole(LAYER, tone(40), RATE)
    high = fx.process_whole(LAYER, tone(2000), RATE)
    assert rms(low[:, RATE // 2:]) < 0.05 * rms(tone(40))
    assert rms(high[:, RATE // 2:]) == pytest.approx(rms(tone(2000)), rel=0.02)


@pytest.mark.parametrize("sizes", [[1024], [1, 7, 333, 1000], [4096, 3]])
def test_output_does_not_depend_on_block_boundaries(sizes):
    x = noise(1.0, channels=2, seed=3).astype(np.float64)
    expected = fx.process_whole(LAYER, x, RATE)
    track = type("T", (), {"id": "t", "fx": (LAYER,)})()
    state = fx.FxState(RATE)
    out, pos, i = [], 0, 0
    while pos < x.shape[1]:
        n = min(sizes[i % len(sizes)], x.shape[1] - pos)
        out.append(state.process(track, x[:, pos:pos + n].copy(), pos))
        pos += n
        i += 1
    np.testing.assert_allclose(np.concatenate(out, axis=1), expected, rtol=0, atol=1e-12)


def test_bypass_returns_the_dry_signal_exactly():
    x = noise(0.2, channels=2).astype(np.float64)
    off = FxLayer("highpass", 200.0, True)
    track = type("T", (), {"id": "t", "fx": (off,)})()
    np.testing.assert_array_equal(fx.FxState(RATE).process(track, x.copy(), 0), x)
    np.testing.assert_array_equal(fx.process_whole(off, x, RATE), x)


def test_a_seek_restarts_the_filter_from_silence():
    x = noise(0.5, channels=2, seed=1).astype(np.float64)
    track = type("T", (), {"id": "t", "fx": (LAYER,)})()
    state = fx.FxState(RATE)
    state.process(track, x[:, :4000].copy(), 0)
    jumped = state.process(track, x[:, 9000:9500].copy(), 9000)  # not the next block
    fresh = fx.FxState(RATE).process(track, x[:, 9000:9500].copy(), 9000)
    np.testing.assert_array_equal(jumped, fresh)


def test_turning_a_layer_off_and_on_starts_clean():
    x = noise(0.3, channels=2, seed=2).astype(np.float64)
    on = type("T", (), {"id": "t", "fx": (LAYER,)})()
    off = type("T", (), {"id": "t", "fx": (FxLayer("highpass", 200.0, True),)})()
    state = fx.FxState(RATE)
    state.process(on, x[:, :1000].copy(), 0)
    state.process(off, x[:, 1000:2000].copy(), 1000)
    again = state.process(on, x[:, 2000:3000].copy(), 2000)
    fresh = fx.FxState(RATE).process(on, x[:, 2000:3000].copy(), 2000)
    np.testing.assert_array_equal(again, fresh)


def project_with_fx(layers):
    arrays = {"m": tone(60, 2.0)[:1]}
    p = project_with(arrays)
    tid = p.tracks[0].id
    return ops.set_track(p, tid, fx=layers), arrays


def test_layers_are_saved_with_the_project_and_old_files_are_unchanged():
    p, _ = project_with_fx([{"kind": "highpass", "hz": 120.0, "bypass": True}])
    again = Project.from_dict(p.to_dict())
    assert again.tracks[0].fx == (FxLayer("highpass", 120.0, True),)
    assert again == p
    plain = ops.set_track(p, p.tracks[0].id, fx=[])
    assert "fx" not in plain.tracks[0].to_dict()


@pytest.mark.parametrize("bad", [{"kind": "reverb"}, {"hz": 5.0}, {"hz": 9000.0},
                                 {"hz": float("nan")}])
def test_a_bad_layer_is_refused(bad):
    p, _ = project_with_fx([])
    with pytest.raises(EditError):
        ops.set_track(p, p.tracks[0].id, fx=[{"kind": "highpass", "hz": 80.0, **bad}])


def test_the_mixer_applies_layers_only_when_asked():
    p, arrays = project_with_fx([{"kind": "highpass", "hz": 300.0}])
    store = MemoryStore(arrays)
    dry = mixer.mix(p, store, 0, 24000)
    wet = mixer.mix(p, store, 0, 24000, fx.FxState(RATE))
    assert rms(dry[:, 12000:]) > 5 * rms(wet[:, 12000:])  # a 60 Hz tone through 300 Hz
    np.testing.assert_array_equal(dry, mixer.mix(p, store, 0, 24000))


def test_the_engine_plays_the_layer_at_1x_and_bypass_is_dry(rig, clock):
    p, arrays = project_with_fx([{"kind": "highpass", "hz": 300.0}])
    engine, session, _ = make(rig, clock, arrays)
    session.state = p
    engine.set_project(p)
    engine.play(0)
    wet = np.concatenate([engine._render(1024) for _ in range(20)])[4096:]
    dry_p = ops.set_track(p, p.tracks[0].id, fx=[{"kind": "highpass", "hz": 300.0,
                                                 "bypass": True}])
    session.state = dry_p
    engine.set_project(dry_p)
    engine.play(0)
    dry = np.concatenate([engine._render(1024) for _ in range(20)])[4096:]
    assert rms(dry) > 5 * rms(wet)
