"""Live short-term loudness uses the shared BS.1770 meter, with bounded state."""

import numpy as np
import pytest
from speechmix.meter import IntegratedMeter

from kuulas import meter

RATE = 48000


def tone(seconds, gain=0.1):
    mono = gain * np.sin(2 * np.pi * 1000 * np.arange(round(seconds * RATE)) / RATE)
    return np.column_stack((mono, mono)).astype(np.float32)


def test_short_term_waits_for_three_seconds_and_matches_shared_meter():
    live = meter.ShortTermAccumulator(RATE)
    audio = tone(3)
    assert live.add(audio[:RATE]) is None
    value = live.add(audio[RATE:])
    reference = IntegratedMeter(RATE)
    reference.add(audio.T)
    assert value == pytest.approx(reference.short_term()[-1], abs=0.01)


def test_short_term_is_last_three_seconds_not_all_playback():
    live = meter.ShortTermAccumulator(RATE)
    loud = live.add(tone(3, 0.3))
    quiet = live.add(tone(3, 0.03))
    assert quiet == pytest.approx(loud - 20, abs=0.1)
    assert len(live.shared._powers) <= 30
    assert len(live.shared._speech) <= 30


def test_short_term_silence_is_json_safe_floor():
    live = meter.ShortTermAccumulator(RATE)
    assert live.add(np.zeros((3 * RATE, 2), dtype=np.float32)) == meter.FLOOR_DB


def test_live_meter_copies_reused_audio_buffer_and_runs_dsp_off_callback(monkeypatch):
    import threading  # noqa: PLC0415

    ready = threading.Event()
    seen = []

    class Accumulator:
        def __init__(self, _rate):
            pass

        def add(self, block):
            seen.append(float(block[0, 0]))
            ready.set()
            return -23.0

    monkeypatch.setattr(meter, "ShortTermAccumulator", Accumulator)
    live = meter.LiveShortTerm()
    audio = np.ones((128, 2), dtype=np.float32)
    try:
        live.offer(audio, RATE, 1)
        audio[:] = 0
        assert not seen  # enqueueing performs no DSP in the callback
        live.read()
        assert ready.wait(2)
        assert seen == [1.0]
        live.reset()
        assert live.value is None
    finally:
        live.close()
