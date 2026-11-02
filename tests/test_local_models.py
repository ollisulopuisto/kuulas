"""The setup dialog trusts only a usable SDK receipt, not a stale marker file."""

import json
from pathlib import Path

import pytest

from kuulas import local_models


@pytest.fixture
def setup(tmp_path, monkeypatch):
    receipt = tmp_path / "cache" / "installation.json"
    monkeypatch.setenv("ORUKEET_INSTALLATION", str(receipt))
    monkeypatch.setattr(local_models.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(local_models.platform, "machine", lambda: "arm64")
    return tmp_path, receipt


def write_receipt(path, *, model_path, runtime_path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": str(model_path), "runtime": str(runtime_path),
                                "device": "cpu"}))


def test_default_receipt_matches_the_podcast_cli_cache_path(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("ORUKEET_INSTALLATION", raising=False)
    assert local_models.installation_file() == (
        tmp_path / ".cache" / "orukeet" / "installation.json")


def test_readiness_requires_sdk_receipt_and_every_referenced_path(setup):
    root, receipt = setup
    model_file = root / "cache" / "weights" / "model.bin"
    runtime_dir = root / "cache" / "runtime"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"weights")
    runtime_dir.mkdir()
    assert not local_models.status()["ready"]

    write_receipt(receipt, model_path=model_file, runtime_path=runtime_dir)
    assert local_models.status()["ready"]

    model_file.unlink()
    assert not local_models.status()["ready"]
    model_file.write_bytes(b"restored")
    runtime_dir.rmdir()
    assert not local_models.status()["ready"]


@pytest.mark.parametrize("contents", ["{", "[]", '{"model":"x"}',
                                       '{"model":"/gone","runtime":"/gone",'
                                       '"device":"cpu"}',
                                       '{"model":"relative","runtime":"/tmp",'
                                       '"device":"cpu"}',
                                       '{"model":"/bad\\u0000path",'
                                       '"runtime":"/tmp","device":"cpu"}'])
def test_invalid_or_stale_receipt_is_not_ready(setup, contents):
    _, receipt = setup
    receipt.parent.mkdir(parents=True)
    receipt.write_text(contents)
    assert not local_models.status()["ready"]


def test_install_command_uses_isolated_environment_and_pinned_sdk(setup):
    _, receipt = setup
    command = local_models.install_command()
    assert command[:3] == ["uv", "run", "--no-project"]
    with_args = [command[i + 1] for i, arg in enumerate(command[:-1]) if arg == "--with"]
    assert local_models.ORUKEET_WHEEL in with_args
    assert local_models.ORUKEET_TORCH in with_args
    assert local_models.ORUKEET_TORCHAUDIO in with_args
    assert command[-8:] == ["orukeet", "install", "--device", "auto", "--cache",
                            str(receipt.parent), "--output", str(receipt)]


def test_install_runs_sdk_installer_and_returns_only_after_files_exist(
        setup, monkeypatch):
    root, receipt = setup
    model_path = root / "cache" / "weights"
    runtime_path = root / "cache" / "runtime"
    calls, reports = [], []

    def run(command, _cwd, on_line, _cancel):
        calls.append(command)
        on_line("Downloading model")
        model_path.mkdir(parents=True)
        runtime_path.mkdir()
        write_receipt(receipt, model_path=model_path, runtime_path=runtime_path)
        return 0

    monkeypatch.setattr(local_models, "run_process", run)
    result = local_models.install(lambda *args: reports.append(args))
    assert result["ready"]
    assert ["orukeet", "install"] in [calls[0][i:i + 2]
                                       for i in range(len(calls[0]) - 1)]
    assert reports[-1][0] == 1.0


def test_install_fails_if_sdk_succeeds_without_a_valid_receipt(setup, monkeypatch):
    monkeypatch.setattr(local_models, "run_process", lambda *_args: 0)
    with pytest.raises(local_models.ModelError) as error:
        local_models.install(lambda *_args: None)
    assert error.value.key == "error.orukeet.receipt"


def test_install_failure_includes_sdk_output(setup, monkeypatch):
    def run(_command, _cwd, on_line, _cancel):
        on_line("model download failed")
        return 2
    monkeypatch.setattr(local_models, "run_process", run)
    with pytest.raises(local_models.ModelError) as error:
        local_models.install(lambda *_args: None)
    assert error.value.key == "error.orukeet.install"
    assert "model download failed" in error.value.params["error"]


def test_install_cancellation_reaches_the_sdk_process(setup, monkeypatch):
    class Cancelled:
        cancelled = True

        def __call__(self, *_args):
            pass

    def run(_command, _cwd, _on_line, cancel):
        assert cancel.is_set()
        return -2

    monkeypatch.setattr(local_models, "run_process", run)
    from kuulas.jobs import JobCancelledError  # noqa: PLC0415
    with pytest.raises(JobCancelledError):
        local_models.install(Cancelled())
