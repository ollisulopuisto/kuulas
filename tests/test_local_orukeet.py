"""Local Orukeet transcription uses its native worker and word timings."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from kuulas import live_engine, local_memory, local_models, transcribe
from kuulas.clock import FLICKS
from kuulas.jobs import JobCancelledError


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # Production limits local Orukeet to Apple silicon; these tests exercise
    # its native worker contract on any host.
    monkeypatch.setattr(local_models.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(local_models.platform, "machine", lambda: "arm64")
    model_file = tmp_path / "orukeet" / "model.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"fixture model")
    runtime = tmp_path / "orukeet" / "runtime"
    runtime.mkdir()
    receipt = tmp_path / "orukeet" / "installation.json"
    receipt.write_text(json.dumps({"model": str(model_file), "runtime": str(runtime),
                                   "device": "cpu"}))
    monkeypatch.setenv("ORUKEET_INSTALLATION", str(receipt))
    monkeypatch.setattr(local_memory, "eligible", lambda: True)
    return model_file


def make_audio(path):
    sf.write(path, np.zeros(32_000, dtype=np.float32), 16_000)
    return path


def test_local_uses_native_orukeet_and_preserves_word_timings(
    model, monkeypatch, tmp_path
):
    receipt = {"model": str(model), "runtime": str(model.parent / "runtime"),
               "device": "cpu"}
    monkeypatch.setattr(live_engine, "read_receipt", lambda: receipt)
    calls, reports = [], []

    def engine_factory(actual_receipt):
        assert actual_receipt == receipt

        def transcribe_chunk(samples, rate):
            calls.append((len(samples), rate))
            return [{"word": "öö", "start": 0.5, "end": 0.7},
                    {"word": "niin", "start": 0.8, "end": 1.0}]

        return transcribe_chunk

    monkeypatch.setattr(live_engine, "warm_engine_factory", engine_factory)
    words = transcribe.local(make_audio(tmp_path / "speech.wav"), progress=reports.append)

    assert [word["w"] for word in words] == ["öö", "niin"]
    assert words[0]["s"] == FLICKS // 2
    assert words[1]["e"] == FLICKS
    assert calls == [(32_000, 16_000)]
    assert reports == [1.0]


def test_missing_sdk_files_are_rejected(model):
    (model.parent / "runtime").rmdir()
    with pytest.raises(transcribe.TranscribeError) as error:
        transcribe.local("speech.wav")
    assert error.value.key == "error.transcribe.orukeet_model"


def test_local_cancel_stops_before_transcribing_a_chunk(model, monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(live_engine, "read_receipt", lambda: {
        "model": str(model), "runtime": str(model.parent / "runtime"), "device": "cpu"})
    monkeypatch.setattr(live_engine, "warm_engine_factory",
                        lambda *_: called.append(True))
    with pytest.raises(JobCancelledError):
        transcribe.local(make_audio(tmp_path / "speech.wav"),
                         progress=SimpleNamespace(cancelled=True))
    assert called == []


def test_native_worker_failure_is_reported_as_local_orukeet_error(
    model, monkeypatch, tmp_path
):
    monkeypatch.setattr(live_engine, "read_receipt", lambda: {
        "model": str(model), "runtime": str(model.parent / "runtime"), "device": "cpu"})

    def fail(_receipt):
        raise RuntimeError("Orukeet failed")

    monkeypatch.setattr(live_engine, "warm_engine_factory", fail)
    with pytest.raises(transcribe.TranscribeError) as error:
        transcribe.local(make_audio(tmp_path / "speech.wav"))
    assert error.value.key == "error.transcribe.orukeet_failed"
    assert "Orukeet failed" in error.value.params["error"]


def test_explicit_low_memory_override_reaches_native_worker(model, monkeypatch, tmp_path):
    monkeypatch.setattr(local_memory, "eligible", lambda: False)
    monkeypatch.setattr(live_engine, "read_receipt", lambda: {
        "model": str(model), "runtime": str(model.parent / "runtime"), "device": "cpu"})
    called = []
    monkeypatch.setattr(live_engine, "warm_engine_factory", lambda *_: (
        called.append(True) or (lambda _samples, _rate: [])))

    assert transcribe.local(make_audio(tmp_path / "speech.wav"),
                            allow_low_memory=True) == []
    assert called == [True]
