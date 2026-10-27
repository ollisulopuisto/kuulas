"""GUI model installation is verified, cancellable and never replaces user files."""

import hashlib
import io
import json
from pathlib import Path

import pytest

from kuulas import local_models
from kuulas.jobs import JobCancelledError


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_ORUKEET_FILE", str(tmp_path / "setup.json"))
    monkeypatch.setattr(local_models, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(local_models.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(local_models.platform, "machine", lambda: "arm64")
    return tmp_path


def model(folder):
    folder.mkdir(parents=True)
    (folder / "config.json").write_text(json.dumps({"target": "EncDecRNNTBPEModel"}))
    (folder / "model.safetensors").write_bytes(b"synthetic weights")
    return folder


def download_fixture(monkeypatch):
    data = {"config.json": json.dumps({"target": "EncDecRNNTBPEModel"}).encode(),
            "model.safetensors": b"synthetic weights", "NOTICE.md": b"attribution"}
    manifest = tuple(
        local_models.ModelFile(name, len(raw), hashlib.sha256(raw).hexdigest())
        for name, raw in data.items())
    monkeypatch.setattr(local_models, "FILES", manifest)
    return data


def test_select_existing_model_is_remembered_without_touching_it(home):
    chosen = model(home / "custom")
    before = (chosen / "model.safetensors").read_bytes()
    local_models.select_model(str(chosen))
    assert local_models.status()["ready"]
    assert local_models.model_path() == chosen
    assert (chosen / "model.safetensors").read_bytes() == before


def test_invalid_selection_leaves_previous_model_selected(home):
    chosen = model(home / "custom")
    local_models.select_model(str(chosen))
    with pytest.raises(local_models.ModelError):
        local_models.select_model(str(home / "missing"))
    assert local_models.model_path() == chosen


def test_legacy_folder_is_reused_and_broken_link_does_not_block_install(home):
    legacy = model(Path.home() / ".models" / "orukeet-mlx")
    assert local_models.model_path() == legacy
    (legacy / "model.safetensors").unlink()
    assert not local_models.status()["ready"]


def test_verified_install_publishes_and_selects_complete_model(home, monkeypatch):
    data = download_fixture(monkeypatch)
    calls, progress = [], []
    def open_url(url, **_kwargs):
        calls.append(url)
        return io.BytesIO(data[url.rsplit("/", 1)[1]])
    monkeypatch.setattr(local_models, "urlopen", open_url)
    result = local_models.install(lambda share, *_args: progress.append(share))
    path = Path(result["path"])
    assert path != Path.home() / ".models" / "orukeet-mlx"
    assert local_models.model_path() == path
    assert (path / "NOTICE.md").read_bytes() == b"attribution"
    assert all(local_models.REVISION in url for url in calls)
    assert progress[-1] == 1
    assert progress == sorted(progress)
    assert local_models.status()["ready"]
    assert not list(path.parent.glob(".orukeet-*"))


@pytest.mark.parametrize("failure", ["hash", "truncated", "network", "cancel"])
def test_failed_install_keeps_existing_model_and_cleans_staging(
        home, monkeypatch, failure):
    chosen = model(home / "custom")
    local_models.select_model(str(chosen))
    data = download_fixture(monkeypatch)
    def open_url(url, **_kwargs):
        if failure == "network":
            raise OSError("offline")
        raw = data[url.rsplit("/", 1)[1]]
        if failure == "hash":
            raw = b"X" * len(raw)
        elif failure == "truncated":
            raw = raw[:-1]
        return io.BytesIO(raw)
    monkeypatch.setattr(local_models, "urlopen", open_url)
    def progress(_share, *_args):
        if failure == "cancel":
            raise JobCancelledError
    with pytest.raises((local_models.ModelError, JobCancelledError)):
        local_models.install(progress)
    assert local_models.model_path() == chosen
    assert (chosen / "model.safetensors").read_bytes() == b"synthetic weights"
    assert not list((home / "models").glob(".orukeet-*"))


def test_old_whisper_failure_points_to_gui_setup_in_both_languages():
    from kuulas import bgjobs, messages  # noqa: PLC0415

    for language in ("en", "fi"):
        messages.set_language(language)
        error = bgjobs._error_of({"key": "error.transcribe.missing_extra",
                                 "text": "Install faster-whisper from the terminal."})
        assert "Orukeet" in error["text"]
        assert "faster-whisper" not in error["text"]


def test_insufficient_space_does_not_change_model_selection(home, monkeypatch):
    from types import SimpleNamespace  # noqa: PLC0415

    chosen = model(home / "custom")
    local_models.select_model(str(chosen))
    monkeypatch.setattr(local_models.shutil, "disk_usage",
                        lambda _path: SimpleNamespace(free=0))
    with pytest.raises(local_models.ModelError) as error:
        local_models.install(lambda *_args: None)
    assert error.value.key == "error.orukeet.space"
    assert local_models.model_path() == chosen


def test_install_supplies_trusted_roots_without_machine_certificate_paths(
        home, monkeypatch):
    import ssl  # noqa: PLC0415

    monkeypatch.setenv("SSL_CERT_FILE", str(home / "absent.pem"))
    monkeypatch.setenv("SSL_CERT_DIR", str(home / "absent-certs"))
    data = download_fixture(monkeypatch)
    contexts = []
    def open_url(url, **kwargs):
        context = kwargs["context"]
        contexts.append(context)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname
        assert context.get_ca_certs(), "bundled Python must carry trusted CA roots"
        return io.BytesIO(data[url.rsplit("/", 1)[1]])
    monkeypatch.setattr(local_models, "urlopen", open_url)
    assert local_models.install(lambda *_args: None)["ready"]
    assert len(contexts) == len(data)


def test_invalid_certificate_never_retries_without_verification(home, monkeypatch):
    import ssl  # noqa: PLC0415

    chosen = model(home / "custom")
    local_models.select_model(str(chosen))
    download_fixture(monkeypatch)
    calls = []
    def open_url(url, **kwargs):
        calls.append((url, kwargs))
        raise ssl.SSLCertVerificationError("untrusted certificate")
    monkeypatch.setattr(local_models, "urlopen", open_url)
    with pytest.raises(local_models.ModelError) as error:
        local_models.install(lambda *_args: None)
    assert error.value.key == "error.orukeet.download"
    assert len(calls) == 1
    assert local_models.model_path() == chosen
