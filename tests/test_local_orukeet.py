"""Local transcription uses the shared Orukeet CLI, never Whisper or Colab."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from kuulas import colab_transcribe, transcribe
from kuulas.clock import FLICKS
from kuulas.jobs import JobCancelledError


@pytest.fixture
def model(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    folder = tmp_path / ".models" / "orukeet-mlx"
    folder.mkdir(parents=True)
    return folder


def test_local_uses_shared_orukeet_and_preserves_words(model, monkeypatch, tmp_path):
    calls, reports = [], []
    monkeypatch.setattr(colab_transcribe, "default_command", lambda: [
        "uv", "run", "--project", "/podcast/colab-transcribe", "colab-transcribe"])

    def process(cmd, cwd, on_line, cancel):
        calls.append(cmd)
        assert not cancel.is_set()
        on_line('@@kuulas {"event":"progress","percent":50}')
        dest = Path(cmd[cmd.index("--json") + 1]) / "speech.words.json"
        dest.write_text(json.dumps({"version": 1, "timing": "orukeet", "language": "fi",
            "words": [{"w": "öö", "s": 0.5, "e": 0.7},
                      {"w": "niin", "s": 0.8, "e": 1.0}]}))
        return 0

    monkeypatch.setattr(transcribe, "_run_local_process", process, raising=False)
    words = transcribe.local(tmp_path / "speech.wav", model="small",
                             progress=reports.append)
    assert [w["w"] for w in words] == ["öö", "niin"]
    assert words[0]["s"] == FLICKS // 2
    cmd = calls[0]
    assert cmd[cmd.index("--backend") + 1] == "orukeet"
    assert "--model" not in cmd
    assert cmd[cmd.index("--orukeet-model") + 1] == str(model)
    assert cmd[cmd.index("--extra") + 1] == "orukeet"
    with_args = [cmd[i + 1] for i, word in enumerate(cmd[:-1]) if word == "--with"]
    assert "torch==2.8.0" in with_args
    assert "torchaudio==2.8.0" in with_args
    assert "--align" not in cmd
    assert reports[-1] == 1.0


def test_missing_orukeet_model_does_not_fall_back_to_parakeet(model):
    model.rmdir()
    with pytest.raises(transcribe.TranscribeError) as error:
        transcribe.local("speech.wav")
    assert error.value.key == "error.transcribe.orukeet_model"


def test_local_cancel_reaches_process(model, monkeypatch):
    def process(_cmd, _cwd, _line, cancel):
        assert cancel.is_set()
        return 1
    monkeypatch.setattr(transcribe, "_run_local_process", process, raising=False)
    with pytest.raises(JobCancelledError):
        transcribe.local("speech.wav", progress=SimpleNamespace(cancelled=True))


def test_local_tool_failure_is_reported_as_local_orukeet_error(model, monkeypatch):
    def process(_cmd, _cwd, line, _cancel):
        line("Orukeet failed")
        return 1
    monkeypatch.setattr(transcribe, "_run_local_process", process, raising=False)
    with pytest.raises(transcribe.TranscribeError) as error:
        transcribe.local("speech.wav")
    assert error.value.key == "error.transcribe.orukeet_failed"
    assert "Orukeet failed" in error.value.params["error"]


def test_packaged_command_installs_orukeet_runtime_in_isolated_environment(
    model, monkeypatch
):
    monkeypatch.setattr(colab_transcribe, "default_command", lambda: [
        "uvx", "--from", "git+https://example.invalid/tool", "colab-transcribe"])
    def process(cmd, _cwd, _line, _cancel):
        with_args = [cmd[i + 1] for i, word in enumerate(cmd[:-1]) if word == "--with"]
        assert any(value.startswith("https://github.com/Oruk-AI/orukeet/")
                   for value in with_args)
        assert "torch==2.8.0" in with_args
        assert "torchaudio==2.8.0" in with_args
        raise FileNotFoundError("uvx")
    monkeypatch.setattr(transcribe, "_run_local_process", process, raising=False)
    with pytest.raises(transcribe.TranscribeError) as error:
        transcribe.local("speech.wav")
    assert error.value.key == "error.transcribe.orukeet_failed"


def test_explicit_override_reaches_shared_cli(model, monkeypatch):
    from kuulas import local_memory  # noqa: PLC0415
    monkeypatch.setattr(local_memory, "physical_memory", lambda: 8 * 1024**3)
    def process(cmd, *_):
        assert "--allow-low-memory" in cmd
        raise FileNotFoundError("fixture")
    monkeypatch.setattr(transcribe, "_run_local_process", process)
    with pytest.raises(transcribe.TranscribeError) as error:
        transcribe.local("speech.wav", allow_low_memory=True)
    assert error.value.key == "error.transcribe.orukeet_failed"
