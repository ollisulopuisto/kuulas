"""The detached transcription worker (WP79): fake engines only, no Colab, no audio.

The in-process tests call ``run_job`` with a fake engine; the process tests start
the real worker program with a fake ``colab-transcribe`` script."""

import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from kuulas import bgjobs, colab_transcribe, messages
from kuulas.clock import FLICKS
from kuulas.transcribe_worker import run_job

WORDS = [{"w": "hello", "s": FLICKS // 4, "e": FLICKS // 2, "spk": ""}]

FAKE = textwrap.dedent('''
    import json, os, sys, time
    argv = sys.argv[1:]
    audio = [argv[i + 1] for i, a in enumerate(argv) if a == "--audio"]
    folder = argv[argv.index("--json") + 1]
    print("PROGRESS 10 uploading", flush=True)
    if os.environ.get("FAKE_MODE") == "hang":
        time.sleep(60)
    for path in audio:
        stem = os.path.splitext(os.path.basename(path))[0]
        doc = {"version": 1, "timing": "ctc-v1", "language": "fi",
               "words": [{"w": stem, "s": 0.25, "e": 0.5}]}
        with open(os.path.join(folder, stem + ".words.json"), "w") as f:
            json.dump(doc, f)
    print("PROGRESS 100 done", flush=True)
''')


@pytest.fixture(autouse=True)
def english():
    messages.set_language("en")
    yield
    messages.set_language("en")


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "P.kuulas"


def make(folder, backend="local", names=("a", "b"), settings=None):
    items = [{"id": f"m{i}", "name": f"{n}.wav", "path": str(folder / f"{n}.wav")}
             for i, n in enumerate(names)]
    return bgjobs.create_job(
        folder, backend=backend, items=items, previous={i["id"]: None for i in items},
        names=[i["name"] for i in items], model="small", language="fi",
        settings=settings)


def status(folder, job_id):
    return json.loads(bgjobs.status_file(folder, job_id).read_text())


def test_local_success_writes_one_result_per_media_in_the_contract_shape(folder):
    job_id = make(folder)

    def local(path, model="small", language=None, progress=None, **kwargs):
        progress(0.5)
        return WORDS

    assert run_job(bgjobs.job_file(folder, job_id), local=local) == "completed"
    done = status(folder, job_id)
    assert done["state"] == "completed"
    assert done["progress"] == 1.0
    assert done["pid"] == os.getpid()
    assert done["finished"]
    for media_id in ("m0", "m1"):
        # The strict reader of the Colab contract accepts what the worker wrote.
        read = colab_transcribe.read_words_json(
            bgjobs.result_file(folder, job_id, media_id))
        assert read["words"][0]["w"] == "hello"
        assert read["words"][0]["s"] == FLICKS // 4


def test_colab_success_keeps_timing_and_language(folder):
    job_id = make(folder, "colab", settings={"command": ["x"]})

    def colab(items, params, settings, report, cancel):
        assert params == {"model": "small", "language": "fi"}
        assert settings == {"command": ["x"]}
        report(0.5, "halfway", False)
        return {"results": {i["id"]: {"words": WORDS, "timing": "ctc-v1",
                                      "language": "fi", "rejected": 0}
                            for i in items}}

    assert run_job(bgjobs.job_file(folder, job_id), colab=colab) == "completed"
    read = colab_transcribe.read_words_json(bgjobs.result_file(folder, job_id, "m1"))
    assert read["timing"] == "ctc-v1"
    assert read["language"] == "fi"


def test_failure_is_recorded_with_its_message_key(folder):
    job_id = make(folder, "colab")

    def colab(*_args):
        raise colab_transcribe.ColabError("error.colab.failed", code=2, tail="no GPU")

    assert run_job(bgjobs.job_file(folder, job_id), colab=colab) == "failed"
    done = status(folder, job_id)
    assert done["state"] == "failed"
    assert done["error"]["key"] == "error.colab.failed"
    assert done["error"]["params"]["tail"] == "no GPU"
    assert not list(bgjobs.jobs_dir(folder).glob("*.words.json"))
    shown = bgjobs.describe(folder, job_id)
    assert "no GPU" in shown["error"]["text"]


def test_an_unexpected_error_is_a_failed_job_not_a_crash(folder):
    job_id = make(folder)

    def local(*_args, **_kwargs):
        raise ZeroDivisionError("boom")

    assert run_job(bgjobs.job_file(folder, job_id), local=local) == "failed"
    assert status(folder, job_id)["error"]["key"] == "error.job.failed"


def test_a_cancel_request_file_stops_the_engine(folder):
    job_id = make(folder)
    started = threading.Event()

    def local(path, model="small", language=None, progress=None, **kwargs):
        started.set()
        deadline = time.monotonic() + 5
        while not progress.cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        return WORDS

    result = []
    thread = threading.Thread(target=lambda: result.append(
        run_job(bgjobs.job_file(folder, job_id), local=local)))
    thread.start()
    assert started.wait(2)
    bgjobs.request_cancel(folder, job_id)
    thread.join(5)
    assert result == ["cancelled"]
    assert status(folder, job_id)["state"] == "cancelled"
    assert not list(bgjobs.jobs_dir(folder).glob("*.words.json"))


def test_the_status_file_is_never_half_written(folder):
    job_id = make(folder, names=("a",))
    stop = threading.Event()
    bad = []

    def reader():
        path = bgjobs.status_file(folder, job_id)
        while not stop.is_set():
            try:
                json.loads(path.read_text())
            except FileNotFoundError:
                continue
            except ValueError as e:
                bad.append(str(e))

    def local(path, model="small", language=None, progress=None, **kwargs):
        for i in range(200):
            progress(i / 200, f"line {i} " + "x" * 2000)
        return WORDS

    thread = threading.Thread(target=reader)
    thread.start()
    try:
        run_job(bgjobs.job_file(folder, job_id), local=local, status_interval=0)
    finally:
        stop.set()
        thread.join()
    assert bad == []


def test_a_job_whose_worker_is_gone_is_interrupted(folder):
    job_id = make(folder)
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    bgjobs.write_json_atomic(bgjobs.status_file(folder, job_id), {
        "state": "running", "progress": 0.3, "pid": gone.pid, "message": "",
        "host": bgjobs._hostname()})
    shown = bgjobs.describe(folder, job_id)
    assert shown["state"] == "interrupted"
    assert shown["error"]["key"] == "error.transcribe.interrupted"
    assert shown["media"] == ["m0", "m1"]  # the dock lists what is missing per recording


# -- the real worker program ---------------------------------------------------


def start_worker(folder, tmp_path, mode="ok"):
    script = tmp_path / "fake_colab.py"
    script.write_text(FAKE, encoding="utf-8")
    job_id = make(folder, "colab", names=("a",),
                  settings={"command": [sys.executable, str(script)]})
    env = {**os.environ, "FAKE_MODE": mode}
    proc = subprocess.Popen(  # noqa: S603 - our own module and a fake script
        [sys.executable, "-m", "kuulas.transcribe_worker", "run",
         str(bgjobs.job_file(folder, job_id))],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, env=env)
    return job_id, proc


def wait_for(folder, job_id, wanted, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = bgjobs.read_json(bgjobs.status_file(folder, job_id)) or {}
        if got.get("state") in wanted and (
                got["state"] != "running" or got.get("message")):
            return got
        time.sleep(0.05)
    raise AssertionError(f"job did not reach {wanted}")


def test_the_worker_program_runs_a_job_to_the_end(folder, tmp_path):
    job_id, proc = start_worker(folder, tmp_path)
    assert proc.wait(15) == 0
    assert status(folder, job_id)["state"] == "completed"
    assert bgjobs.result_file(folder, job_id, "m0").is_file()


def test_the_worker_runs_in_its_own_session(folder, tmp_path):
    job_id, proc = start_worker(folder, tmp_path, "hang")
    try:
        got = wait_for(folder, job_id, {"running"})
        assert got["pid"] == proc.pid
        assert os.getsid(proc.pid) == proc.pid  # a session leader, not our child group
        assert os.getsid(proc.pid) != os.getsid(0)
    finally:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def test_sigterm_cancels_and_stops_the_tool(folder, tmp_path):
    job_id, proc = start_worker(folder, tmp_path, "hang")
    wait_for(folder, job_id, {"running"})
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(40) == 0
    assert status(folder, job_id)["state"] == "cancelled"
    assert not list(bgjobs.jobs_dir(folder).glob("*.words.json"))


def test_a_killed_worker_leaves_an_interrupted_job(folder, tmp_path):
    job_id, proc = start_worker(folder, tmp_path, "hang")
    wait_for(folder, job_id, {"running"})
    os.killpg(proc.pid, signal.SIGKILL)  # the worker and the tool it started
    proc.wait()
    shown = bgjobs.describe(folder, job_id)
    assert shown["state"] == "interrupted"
    assert Path(bgjobs.job_file(folder, job_id)).is_file()  # it can be restarted
