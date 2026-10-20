"""The output latency numbers (latency.py): pure, no device."""

from types import SimpleNamespace

import pytest

from kuulas import latency


def test_callback_timing_is_the_mean_gap_and_its_spread():
    mean, spread = latency.callback_timing([0.0, 0.020, 0.040, 0.066])
    assert mean == pytest.approx(22.0)
    assert spread == pytest.approx(2.828, abs=0.001)


def test_callback_timing_needs_a_few_callbacks():
    assert latency.callback_timing([]) == (None, None)
    assert latency.callback_timing([1.0, 1.02]) == (None, None)


def test_report_compares_the_estimate_with_block_plus_dac_lead():
    numbers = latency.report(setting="low", stream_latency_s=0.0348, blocksize=1024,
                             device_rate=48000, callback_times=[0, 0.0213, 0.0426],
                             dac_leads=[0.0147, 0.0147])
    assert numbers["setting"] == "low"
    assert numbers["stream_ms"] == 34.8
    assert numbers["block_ms"] == 21.33
    assert numbers["dac_lead_ms"] == 14.7
    assert numbers["estimate_ms"] == 34.8
    assert numbers["measured_ms"] == 36.03
    assert numbers["callback_ms"] == 21.3
    assert numbers["jitter_ms"] == 0.0


def test_report_without_dac_times_measures_nothing():
    numbers = latency.report(setting="high", stream_latency_s=0.02, blocksize=512,
                             device_rate=48000, callback_times=[], dac_leads=[])
    assert numbers["dac_lead_ms"] is None
    assert numbers["measured_ms"] is None
    assert numbers["callback_ms"] is None


@pytest.mark.parametrize(("info", "expected"), [
    (SimpleNamespace(outputBufferDacTime=5.015, currentTime=5.0), 0.015),
    (SimpleNamespace(outputBufferDacTime=0.0, currentTime=5.0), None),  # not filled in
    (SimpleNamespace(outputBufferDacTime=4.0, currentTime=5.0), None),  # before now
    (SimpleNamespace(outputBufferDacTime=9.0, currentTime=5.0), None),  # seconds away
    (None, None),  # a test's callback
])
def test_dac_lead_trusts_only_sane_times(info, expected):
    got = latency.dac_lead(info)
    if expected is None:
        assert got is None
    else:
        assert got == pytest.approx(expected)
