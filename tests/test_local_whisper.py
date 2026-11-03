"""Kuulas's on-device Whisper engine; model and alignment are injected in unit tests."""

from types import SimpleNamespace

import pytest

from kuulas import local_whisper
from kuulas.clock import FLICKS


def test_whisper_uses_turbo_word_timestamps_and_refines_with_wordalign(
    monkeypatch, tmp_path
):
    audio = tmp_path / "speech.wav"
    audio.touch()
    calls = {}
    segment = SimpleNamespace(
        start=0.0,
        end=1.0,
        words=[SimpleNamespace(word=" hello", start=0.1, end=0.5)],
    )

    class FakeModel:
        def __init__(self, model, **kwargs):
            calls["model"] = model
            calls["model_options"] = kwargs

        def transcribe(self, path, **kwargs):
            calls["path"] = path
            calls["options"] = kwargs
            return iter([segment]), SimpleNamespace(duration=1.0)

    monkeypatch.setattr(local_whisper, "_model_factory", lambda: FakeModel)
    monkeypatch.setattr(
        local_whisper,
        "_align_words",
        lambda path, raw, progress: ([{"word": "hello", "start": 0.16,
                                      "end": 0.5}], 0),
    )
    progress = []

    words = local_whisper.local(audio, progress=progress.append)

    assert calls["model"] == "large-v3-turbo"
    assert calls["model_options"]["compute_type"] == "int8"
    assert calls["path"] == str(audio)
    assert calls["options"]["word_timestamps"] is True
    assert calls["options"]["vad_filter"] is True
    assert words == [{"w": "hello", "s": round(0.16 * FLICKS),
                      "e": round(0.5 * FLICKS), "spk": ""}]
    assert progress[-1] == 1.0


def test_whisper_fails_when_word_alignment_is_unavailable(monkeypatch, tmp_path):
    audio = tmp_path / "speech.wav"
    audio.touch()
    segment = SimpleNamespace(
        start=0.0,
        end=1.0,
        words=[SimpleNamespace(word=" okay", start=0.2, end=0.6)],
    )

    class FakeModel:
        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, *_args, **_kwargs):
            return iter([segment]), SimpleNamespace(duration=1.0)

    monkeypatch.setattr(local_whisper, "_model_factory", lambda: FakeModel)
    def fail_alignment(*_args):
        raise RuntimeError

    monkeypatch.setattr(local_whisper, "_align_words", fail_alignment)

    with pytest.raises(local_whisper.WhisperError, match="alignment"):
        local_whisper.local(audio)



def test_alignment_worker_is_routed_by_app_launcher(monkeypatch):
    import sys  # noqa: PLC0415

    from kuulas import bundle, whisper_align_worker  # noqa: PLC0415

    args = ["audio.wav", "raw.json", "out.json"]
    seen = []
    monkeypatch.setattr(sys, "argv",
                        ["Kuulas", "-m", "kuulas.whisper_align_worker", *args])
    monkeypatch.setattr(whisper_align_worker, "main", lambda argv: seen.append(argv) or 0)
    assert bundle.main() == 0
    assert seen == [args]
