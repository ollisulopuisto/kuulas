"""Input LUFS reads only flushed audio outside the standalone recorder."""

import json

import numpy as np
import pytest
import soundfile as sf
from speechmix.meter import IntegratedMeter

from kuulas.record_loudness import RecordingLoudnessReader

RATE = 48000


def write_take(folder, seconds=3, *, gains=(0.1, 0.01), frames=None):
    files = {}
    for name, gain in zip(("Host", "Guest"), gains, strict=True):
        audio = gain * np.sin(2 * np.pi * 1000 * np.arange(seconds * RATE) / RATE)
        sf.write(folder / f"Take-{name}.wav", audio, RATE, subtype="PCM_24")
        files[name] = {"file": f"Take-{name}.wav", "frames": frames or len(audio)}
    sidecar = {"segments": [{"start_frame": 0, "files": files}]}
    (folder / "Take.take.json").write_text(json.dumps(sidecar))


def test_input_lufs_waits_for_three_seconds_and_uses_channel_audio(tmp_path):
    write_take(tmp_path, 3, frames=RATE)
    reader = RecordingLoudnessReader()
    assert reader.read(tmp_path, "Take", RATE, ["Host", "Guest"], now=0) == [None, None]
    write_take(tmp_path, 3)
    values = reader.read(tmp_path, "Take", RATE, ["Host", "Guest"], now=1)
    reference = IntegratedMeter(RATE)
    audio, _ = sf.read(tmp_path / "Take-Host.wav", dtype="float32", always_2d=True)
    reference.add(audio.T)
    assert values[0] == pytest.approx(reference.short_term()[-1], abs=0.01)
    assert values[1] == pytest.approx(values[0] - 20, abs=0.02)


def test_stale_and_missing_audio_are_pending_without_touching_other_files(tmp_path):
    write_take(tmp_path)
    other_before = (tmp_path / "Take-Guest.wav").read_bytes()
    reader = RecordingLoudnessReader()
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=0)[0] is not None
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=4) == [None]
    (tmp_path / "Take-Host.wav").unlink()
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=5) == [None]
    assert (tmp_path / "Take-Guest.wav").read_bytes() == other_before


def test_sidecar_cannot_make_the_meter_read_outside_recordings(tmp_path):
    outside = tmp_path / "outside.wav"
    sf.write(outside, np.ones(3 * RATE), RATE)
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "Take.take.json").write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start_frame": 0,
                        "files": {"Host": {"file": "../outside.wav", "frames": 3 * RATE}},
                    }
                ]
            }
        )
    )
    assert RecordingLoudnessReader().read(folder, "Take", RATE, ["Host"], now=0) == [None]


def test_background_reader_closes_without_writing_or_stopping_capture(tmp_path):
    from recorder_helpers import wait_until  # noqa: PLC0415

    from kuulas.record_loudness import RecordingLoudness  # noqa: PLC0415

    write_take(tmp_path)
    before = (tmp_path / "Take-Host.wav").read_bytes()
    meter = RecordingLoudness()
    try:
        meter.observe(tmp_path, "Take", RATE, ["Host"])
        wait_until(lambda: meter.read()[0] is not None, timeout=5)
        assert meter.read()[0] < -10
    finally:
        meter.close()
    assert not meter._thread.is_alive()
    assert meter.read() == []
    assert (tmp_path / "Take-Host.wav").read_bytes() == before


def test_gap_between_segments_resets_the_three_second_window(tmp_path):
    write_take(tmp_path)
    reader = RecordingLoudnessReader()
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=0)[0] is not None
    path = tmp_path / "Take-Host~2.wav"
    sf.write(path, np.full(RATE, 0.1), RATE)
    sidecar_path = tmp_path / "Take.take.json"
    sidecar = json.loads(sidecar_path.read_text())
    sidecar["segments"].append(
        {"start_frame": 5 * RATE, "files": {"Host": {"file": path.name, "frames": RATE}}}
    )
    sidecar_path.write_text(json.dumps(sidecar))
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=1) == [None]


def test_reader_reports_persistent_failure_once_and_reports_again_after_recovery(
    tmp_path, monkeypatch, caplog
):
    write_take(tmp_path)
    reader = RecordingLoudnessReader()
    original = reader._read_channel

    def fail(*_args):
        raise RuntimeError("meter cache unavailable")

    monkeypatch.setattr(reader, "_read_channel", fail)
    for now in range(10):
        assert reader.read(tmp_path, "Take", RATE, ["Host"], now=now) == [None]
    messages = [r for r in caplog.records if "meter cache unavailable" in r.message]
    assert len(messages) == 1
    assert "Host" in messages[0].message
    assert "Take" in messages[0].message
    assert messages[0].exc_info is not None

    monkeypatch.setattr(reader, "_read_channel", original)
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=11)[0] is not None
    monkeypatch.setattr(reader, "_read_channel", fail)
    assert reader.read(tmp_path, "Take", RATE, ["Host"], now=12) == [None]
    assert len([r for r in caplog.records if "meter cache unavailable" in r.message]) == 2
