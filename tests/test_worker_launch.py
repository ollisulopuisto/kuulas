"""The transcription worker must start in the Briefcase app, where ``sys.executable``
is the bundle's launcher (it always runs ``python -m kuulas <its arguments>``), not a
plain Python.
The launcher is imitated by a shell script."""

import stat
import sys
import time

import pytest

from kuulas import bgjobs, bundle, colab_transcribe

TIMEOUT = 20


def make_job(folder):
    return bgjobs.create_job(
        folder, backend="selftest", items=[{"id": "m0", "name": "a", "path": "a.wav"}],
        previous={}, names=["a"], model=None, language=None, settings=None)


def wait_final(folder, job_id, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    status = {}
    while time.monotonic() < deadline:
        status = bgjobs.read_json(bgjobs.status_file(folder, job_id)) or {}
        if status.get("state") in bgjobs.FINISHED:
            return status
        time.sleep(0.05)
    raise AssertionError(f"the worker never finished: {status}")


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    shim = tmp_path / "Kuulas"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m kuulas "$@"\n',
                    encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setattr(sys, "executable", str(shim))
    return shim


def test_the_worker_runs_when_the_executable_is_the_bundles_launcher(tmp_path, launcher):
    folder = tmp_path / "P.kuulas"
    job_id = make_job(folder)
    bgjobs.start_worker_process(bgjobs.job_file(folder, job_id))
    status = wait_final(folder, job_id)
    assert status["state"] == "completed", status
    assert colab_transcribe.read_words_json(
        bgjobs.result_file(folder, job_id, "m0"))["words"]


def test_worker_arguments_are_recognised_like_the_recorders():
    assert bundle.worker_args(["-m", "kuulas.transcribe_worker", "run", "j.json"]) == [
        "run", "j.json"]
    assert bundle.worker_args(["-m", "kuulas_recorder", "serve"]) is None
    assert bundle.worker_args(["open", "a.kuulas"]) is None


def test_bundle_main_runs_the_worker_and_logs_to_its_own_file(monkeypatch):
    ran = []
    monkeypatch.setattr(bundle, "_run_worker", lambda args: ran.append(args) or 0)
    monkeypatch.setattr(bundle, "_open_log",
                        lambda _home, name="kuulas.log": ran.append(name))
    monkeypatch.setattr(bundle, "resources_dir", lambda _file: bundle.Path("/r"))
    monkeypatch.setattr("sys.argv",
                        ["Kuulas", "-m", "kuulas.transcribe_worker", "run", "j"])
    assert bundle.main() == 0
    assert ran == ["kuulas-worker.log", ["run", "j"]]
