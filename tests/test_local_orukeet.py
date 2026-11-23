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


@pytest.mark.parametrize("rate", [16_000, 48_000])
def test_long_recording_stays_in_30_second_cores_with_bounded_context(
    model, monkeypatch, tmp_path, rate
):
    """Pin the allocation boundary without loading Orukeet or a Metal device.

    A 65-second take has three cores. Adjacent calls share context, but a
    boundary word belongs only to the core containing its midpoint.
    """
    assert transcribe._LOCAL_CHUNK_S == 30
    assert transcribe._LOCAL_CONTEXT_S == 1
    audio = tmp_path / "long-stereo.wav"
    sf.write(audio, np.zeros((65 * rate, 2), dtype=np.float32), rate)
    monkeypatch.setattr(live_engine, "read_receipt", lambda: {"fixture": True})
    calls, closed, reports, seeks, reads = [], [], [], [], []
    sound_file = sf.SoundFile

    class RecordingAudio:
        def __enter__(self):
            self.audio = sound_file(audio)
            self.samplerate = self.audio.samplerate
            return self

        def __exit__(self, *_):
            self.audio.close()

        def __len__(self):
            return len(self.audio)

        def seek(self, frame):
            seeks.append(frame)
            return self.audio.seek(frame)

        def read(self, frames, **kwargs):
            reads.append(frames)
            return self.audio.read(frames, **kwargs)

    monkeypatch.setattr(sf, "SoundFile", lambda _: RecordingAudio())
    output = [
        [{"word": "first", "start": 0.2, "end": 0.4},
         {"word": "boundary-30", "start": 29.8, "end": 30.2}],
        [{"word": "left-context", "start": 0.1, "end": 0.3},
         {"word": "boundary-30", "start": 0.8, "end": 1.2},
         {"word": "boundary-60", "start": 30.8, "end": 31.2}],
        [{"word": "left-context", "start": 0.1, "end": 0.3},
         {"word": "boundary-60", "start": 0.8, "end": 1.2},
         {"word": "last", "start": 5.5, "end": 5.9},
         {"word": "outside-end", "start": 5.9, "end": 6.1}],
    ]

    class Engine:
        def __call__(self, samples, actual_rate):
            assert actual_rate == rate
            assert samples.ndim == 1
            assert samples.dtype == np.float32
            assert len(samples) <= 32 * rate
            calls.append(len(samples))
            return output[len(calls) - 1]

        def close(self):
            closed.append(True)

    monkeypatch.setattr(live_engine, "warm_engine_factory", lambda _: Engine())
    words = transcribe.local(audio, progress=reports.append)

    # First/last context is clipped to the file, interior context is 1 s/side.
    assert calls == reads == [31 * rate, 32 * rate, 6 * rate]
    assert seeks == [0, 29 * rate, 59 * rate]
    assert [word["w"] for word in words] == [
        "first", "boundary-30", "boundary-60", "last"]
    assert [(word["s"], word["e"]) for word in words] == [
        (round(start * FLICKS), round(end * FLICKS))
        for start, end in [(0.2, 0.4), (29.8, 30.2), (59.8, 60.2), (64.5, 64.9)]
    ]
    assert reports == [30 / 65, 60 / 65, 1.0]
    assert closed == [True]
