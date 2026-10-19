"""The live level meter (owner, 2026-10-19): the engine's callback measures the block it
hands to the device, and the control side reads it. No audio device: the fake stream."""

import math

import numpy as np
import pytest
from test_engine import RATE, Clock, install_rig, make, noise

from kuulas import meter


@pytest.fixture
def rig(monkeypatch):
    return install_rig(monkeypatch)


@pytest.fixture
def clock():
    return Clock()


def tone(amp_l: float, amp_r: float, seconds: float = 2.0) -> np.ndarray:
    n = round(seconds * RATE)
    return np.stack([np.full(n, amp_l, np.float32), np.full(n, amp_r, np.float32)])


def db(x: float) -> float:
    return 20 * math.log10(x)


# -- the pure part ------------------------------------------------------------


def test_block_levels_peak_and_rms_per_channel():
    block = np.array([[0.5, -0.25], [-1.0, 0.25], [0.0, 0.25]], dtype=np.float32)
    peak_l, peak_r, ms_l, ms_r = meter.block_levels(block)
    assert (peak_l, peak_r) == (1.0, 0.25)  # a negative peak counts
    assert ms_l == pytest.approx((0.25 + 1.0 + 0.0) / 3)
    assert ms_r == pytest.approx((0.0625 * 3) / 3)


def test_an_empty_block_reads_zero():
    assert meter.block_levels(np.zeros((0, 2), dtype=np.float32)) == (0.0, 0.0, 0.0, 0.0)


def test_to_db_floors_silence_instead_of_minus_infinity():
    assert meter.to_db(0.0) == meter.FLOOR_DB
    assert meter.to_db(1.0) == pytest.approx(0.0)
    assert meter.to_db(0.5) == pytest.approx(-6.0206, abs=1e-3)
    assert meter.to_db(1e-12) == meter.FLOOR_DB


def test_the_hold_follows_a_peak_up_at_once_and_waits_before_falling():
    hold = meter.PeakHold(hold_s=1.0, fall_db_per_s=12.0)
    assert hold.update(-20.0, 0.0) == -20.0
    assert hold.update(-40.0, 0.5) == -20.0  # inside the hold time
    assert hold.update(-40.0, 1.0) == -20.0
    assert hold.update(-40.0, 2.0) == pytest.approx(-32.0)  # 1 s of falling at 12 dB/s
    assert hold.update(-10.0, 2.1) == -10.0  # a new peak takes over


def test_the_hold_stops_falling_at_the_current_level_and_at_the_floor():
    hold = meter.PeakHold(hold_s=0.0, fall_db_per_s=100.0)
    hold.update(-10.0, 0.0)
    assert hold.update(-30.0, 10.0) == -30.0  # never below what is playing now
    assert hold.update(meter.FLOOR_DB, 20.0) == meter.FLOOR_DB


def test_reset_forgets_the_hold():
    hold = meter.PeakHold()
    hold.update(-3.0, 0.0)
    hold.reset()
    assert hold.update(meter.FLOOR_DB, 0.1) == meter.FLOOR_DB


# -- the engine -----------------------------------------------------------------


def test_stopped_the_meter_is_at_the_floor(rig, clock):
    engine, _, _ = make(rig, clock)
    m = engine.meter()
    assert set(m) == {"l", "r", "rms_l", "rms_r", "hold_l", "hold_r"}
    assert set(m.values()) == {meter.FLOOR_DB}


def test_the_callback_measures_what_it_hands_the_device(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(0.5, 0.125)})
    engine.play(0)
    rig.stream.pump()
    m = engine.meter()
    assert m["l"] == pytest.approx(db(0.5), abs=0.01)
    assert m["r"] == pytest.approx(db(0.125), abs=0.01)
    assert m["hold_l"] == pytest.approx(m["l"])


def test_the_peak_covers_every_block_since_the_last_read(rig, clock):
    # A loud block followed by quiet ones, read once: the loud one is not lost.
    loud = np.concatenate([tone(0.9, 0.9, 0.05), tone(0.1, 0.1, 1.9)], axis=1)
    engine, _, _ = make(rig, clock, {"m": loud})
    engine.play(0)
    for _ in range(4):
        rig.stream.pump()
    assert engine.meter()["l"] == pytest.approx(db(0.9), abs=0.01)
    rig.stream.pump()
    assert engine.meter()["l"] == pytest.approx(db(0.1), abs=0.01)  # read cleared it


def test_a_pump_with_the_engine_stopped_reads_silence(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(0.5, 0.5)})
    engine.play(0)
    rig.stream.pump()
    engine.stop()
    rig.stream.pump()
    engine.meter()  # the read after the last loud block
    assert engine.meter()["l"] == meter.FLOOR_DB


def test_over_full_scale_reads_above_zero(rig, clock):
    engine, _, _ = make(rig, clock, {"m": tone(1.5, 0.5)})
    engine.play(0)
    rig.stream.pump()
    assert engine.meter()["l"] > 0.0  # the clip indicator's cue


def test_the_hold_falls_on_the_engines_clock(rig, clock):
    engine, _, _ = make(rig, clock, {"m": np.concatenate(
        [tone(0.5, 0.5, 0.05), tone(0.001, 0.001, 1.95)], axis=1)})
    engine.play(0)
    rig.stream.pump()
    engine.meter()
    clock.now += 0.5
    rig.stream.pump(4096)
    held = engine.meter()
    assert held["hold_l"] == pytest.approx(db(0.5), abs=0.01)  # inside the hold time
    clock.now += 10.0
    rig.stream.pump()
    later = engine.meter()
    assert later["hold_l"] < held["hold_l"] - 5.0
    assert later["hold_l"] >= later["l"]


def test_measuring_only_reads_the_block(rig, clock):
    # The block is the device's output: measuring must not touch it.
    engine, _, _ = make(rig, clock, {"m": noise(2, channels=2)})
    engine.play(0)
    block = np.ascontiguousarray(rig.stream.pump())
    before = block.copy()
    meter.block_levels(block)
    np.testing.assert_array_equal(block, before)  # read-only use of the block


def test_a_failing_meter_never_silences_the_audio(rig, clock, monkeypatch):
    engine, _, _ = make(rig, clock)
    engine.play(0)

    def boom(_block):
        raise RuntimeError("meter bug")

    monkeypatch.setattr(meter, "block_levels", boom)
    out = rig.stream.pump()
    assert np.abs(out).max() > 0  # the block was still written
    assert engine.status()["failed_blocks"] == 0
