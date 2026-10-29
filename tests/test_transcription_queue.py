"""Serialize detached local jobs without starting models; cancellation stays live."""
import os
import subprocess
import sys
import threading

import pytest

from kuulas import bgjobs
from kuulas.jobs import JobCancelledError
from kuulas.local_transcription_queue import slot
from kuulas.transcribe_worker import run_job


def make(folder):
    return bgjobs.create_job(folder, backend='local', items=[
        {'id': 'm', 'name': 'a.wav', 'path': '/fake/a.wav'}], previous={},
        names=['a.wav'], model='small', language='fi', settings=None)


def test_second_local_job_waits_then_runs_without_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv('KUULAS_LOCAL_QUEUE_DIR', str(tmp_path / 'queue'))
    folder = tmp_path / 'P.kuulas'
    first, second = make(folder), make(folder)
    entered, release = threading.Event(), threading.Event()
    second_entered = threading.Event()
    results = []

    def one(*_args, **_kwargs):
        entered.set()
        assert release.wait(3)
        return []

    def two(*_args, **_kwargs):
        second_entered.set()
        return []

    a = threading.Thread(target=lambda: results.append(run_job(
        bgjobs.job_file(folder, first), local=one)))
    b = threading.Thread(target=lambda: results.append(run_job(
        bgjobs.job_file(folder, second), local=two)))
    a.start()
    assert entered.wait(2)
    b.start()
    try:
        assert not second_entered.wait(0.15)
        status = bgjobs.read_json(bgjobs.status_file(folder, second))
        assert status['state'] == 'queued'
        assert status['pid']
    finally:
        release.set()
        a.join(3)
        b.join(3)
    assert second_entered.is_set()
    assert results == ['completed', 'completed']


def test_cancel_queued_job_never_enters_local_engine(tmp_path, monkeypatch):
    monkeypatch.setenv('KUULAS_LOCAL_QUEUE_DIR', str(tmp_path / 'queue'))

    cancel = threading.Event()
    folder = tmp_path / 'P.kuulas'
    job = make(folder)
    entered = []
    result = []
    with slot(cancel):
        worker = threading.Thread(target=lambda: result.append(run_job(
            bgjobs.job_file(folder, job), local=lambda *a, **k: entered.append(True))))
        worker.start()
        bgjobs.request_cancel(folder, job)
        worker.join(3)
    assert not worker.is_alive()
    assert result == ['cancelled']
    assert entered == []


def test_slot_is_released_after_engine_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('KUULAS_LOCAL_QUEUE_DIR', str(tmp_path / 'queue'))
    folder = tmp_path / 'P.kuulas'
    first, second = make(folder), make(folder)

    def fail(*_args, **_kwargs):
        raise RuntimeError('fake engine failure')

    assert run_job(bgjobs.job_file(folder, first), local=fail) == 'failed'
    result = run_job(bgjobs.job_file(folder, second), local=lambda *a, **k: [])
    assert result == 'completed'
    assert list((tmp_path / 'queue').glob('*.wait')) == []


def test_slot_excludes_another_process_and_releases_on_kill(tmp_path, monkeypatch):
    monkeypatch.setenv('KUULAS_LOCAL_QUEUE_DIR', str(tmp_path / 'queue'))
    script = '''
import threading,time
from kuulas.local_transcription_queue import slot
with slot(threading.Event()):
    print('locked',flush=True)
    time.sleep(20)
'''
    child = subprocess.Popen(  # noqa: S603 - fixed test script, no shell
        [sys.executable, '-c', script], stdout=subprocess.PIPE,
                             text=True, env={**os.environ, 'PYTHONPATH': 'src'})
    try:
        assert child.stdout.readline().strip() == 'locked'
        cancel = threading.Event()
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        with pytest.raises(JobCancelledError), slot(cancel):
            pytest.fail('Another process entered the active slot')
        timer.join()
        child.kill()
        child.wait(3)
        with slot(threading.Event()):
            pass
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(3)
