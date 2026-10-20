"""Heavy analysis runs in its own low-priority process (docs/PLAYBACK-PRIORITY.md):
own GIL, nice 10, stopped outright while the editor plays when
the caller is background work. These tests start the real worker process."""

import logging
import os
import sys
import threading
import time

import numpy as np
import pytest
import soundfile as sf

from kuulas import analysis, bundle, loudness_curve, offload, priority, selftest
from kuulas.jobs import JobCancelledError
from kuulas.session import Session
from kuulas.silence_options import SilenceOptionError, SilenceOptions

RATE = 48000
SEC = 6


@pytest.fixture
def process_mode(monkeypatch):
    # conftest runs analysis inline (no test starts a process by accident); these
    # tests are about the process.
    monkeypatch.setattr(offload, "MODE", "process")


def talk(rng, seconds):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(n)).astype(np.float32)


@pytest.fixture
def session(tmp_path):
    rng = np.random.default_rng(5)
    n = SEC * RATE
    anna = np.zeros(n, dtype=np.float32)
    ville = np.zeros(n, dtype=np.float32)
    anna[: int(2.5 * RATE)] = talk(rng, 2.5)
    ville[int(3.5 * RATE):] = talk(rng, 2.5)
    src = tmp_path / "src"
    src.mkdir()
    for name, audio in (("Anna", anna + 0.1 * ville), ("Ville", ville + 0.1 * anna)):
        floor = 0.0003 * rng.standard_normal(n).astype(np.float32)
        sf.write(src / f"{name}.wav", audio + floor, RATE, subtype="PCM_24")
    s = Session(tmp_path / "Episode.kuulas")
    s.import_media([str(src / "Anna.wav"), str(src / "Ville.wav")])
    yield s
    s.close()


def test_the_worker_answers_what_the_editor_would(session, process_mode):
    state = session.state
    inline = analysis.silence_ranges(state, session.store)
    assert inline  # the fixture has two talkers
    got = offload.call("silence_ranges", state, session.store, SilenceOptions())
    assert got == inline


def test_loudness_curves_come_from_the_worker_and_fill_the_cache(session, process_mode):
    state = session.state
    root = session.store.cache_root
    got = offload.call("project_curves", state, session.store, root)
    # The worker wrote the content-keyed cache: the editor's own call now reads it.
    again = loudness_curve.project_curves(state, session.store, root)
    assert got == again
    assert got["mix"]["integrated"] is not None


def test_errors_come_back_with_their_key(session, process_mode):
    with pytest.raises(SilenceOptionError) as err:
        offload.call("silence_ranges", session.state, session.store,
                     SilenceOptions(method="compensated"))
    assert err.value.key == "error.silence.no_hand_mutes"


def test_the_worker_runs_at_a_moderate_priority(process_mode):
    # Not nice 19 and the Darwin background band: on a loaded Mac that starved
    # the worker, which never finished (owner's ps, 2026-10-20: RN, ~5% CPU,
    # 11 minutes). It yields to playback by being stopped while audio plays.
    info = offload.probe({"what": "priority"})
    assert info["nice"] == offload.WORKER_NICE == 10
    assert info["darwin_background"] is False


def test_the_worker_makes_progress_at_its_priority(process_mode):
    # Imports and 0.3 s of CPU: a few seconds of wall time at most on a free
    # machine (measured 2026-10-20: ~0.8 s for the curve worker's imports).
    started = time.monotonic()
    got = offload.probe({"what": "spin", "seconds": 0.3}, pause=False)
    wall = time.monotonic() - started
    assert got["spun"] >= 0.3
    assert got["wall"] < 3.0  # the spin itself was not starved
    assert wall < 15.0


def test_cancel_kills_the_worker(process_mode):
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(JobCancelledError):
        offload.probe({"what": "spin", "seconds": 30}, cancel=cancel)
    assert time.monotonic() - started < 5


def test_background_work_stops_the_worker_while_playing(process_mode, monkeypatch,
                                                        tmp_path):
    state = {"playing": False}
    gate = priority.PlaybackGate(hold_s=0.0, poll_s=0.01)
    gate.watch(lambda: state["playing"])
    monkeypatch.setattr(priority, "GATE", gate)
    events = []
    result = {}
    beat = tmp_path / "beat.txt"

    def run():
        with priority.background(), priority.listening(
                lambda: events.append("pause"), lambda: events.append("resume")):
            result["value"] = offload.probe({"what": "spin", "seconds": 1.0,
                                             "beat": str(beat)})

    def count():
        try:
            return int(beat.read_text(encoding="utf-8") or 0)
        except (OSError, ValueError):
            return -1

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 30
    while count() <= 0 and time.monotonic() < deadline:  # it is spinning
        time.sleep(0.01)
    state["playing"] = True
    time.sleep(0.2)  # the editor looks every 50 ms
    frozen = count()
    time.sleep(0.6)
    assert count() == frozen  # no progress at all while audio plays
    state["playing"] = False
    worker.join(30)
    assert events == ["pause", "resume"]
    assert result["value"]["spun"] >= 1.0  # and it finished its work after


def test_curve_refreshes_while_playing_wait_and_only_the_newest_runs(
        session, process_mode, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from kuulas.engine import Engine  # noqa: PLC0415
    from kuulas.server import create_app  # noqa: PLC0415

    state = {"playing": True}
    gate = priority.PlaybackGate(hold_s=0.0, poll_s=0.01)
    gate.watch(lambda: state["playing"])
    manager = offload.WorkerManager(poll_s=0.01)
    monkeypatch.setattr(offload, "MANAGER", manager)
    ui = tmp_path / "ui"
    ui.mkdir()
    client = TestClient(create_app(session, Engine(session), language="en", ui_dir=ui))
    monkeypatch.setattr(priority, "GATE", gate)  # create_app made GATE watch its engine
    got = {}

    def ask(name):
        got[name] = client.get("/api/loudness-curve")

    first = threading.Thread(target=ask, args=("first",))
    first.start()
    time.sleep(0.5)
    assert manager.alive() == []  # deferred, not started and stopped
    second = threading.Thread(target=ask, args=("second",))
    second.start()
    first.join(10)
    assert got["first"].status_code == 409  # the UI had given up on it already
    assert manager.alive() == []
    state["playing"] = False
    second.join(60)
    assert got["second"].status_code == 200
    assert len(got["second"].json()["tracks"]) == 2
    manager.shutdown()


def test_closing_the_project_ends_its_worker(tmp_path, monkeypatch):
    manager = offload.WorkerManager(poll_s=0.01)
    monkeypatch.setattr(offload, "MANAGER", manager)
    calls = []
    monkeypatch.setattr(manager, "cancel_owner", calls.append)
    session = Session(tmp_path / "Other.kuulas")
    folder = str(session.store.folder)
    session.close()
    assert calls == [folder]
    manager.shutdown()


def test_a_worker_that_cannot_start_falls_back_inline(session, process_mode, monkeypatch,
                                                      caplog):
    monkeypatch.setattr(offload, "worker_argv", lambda *_a: [sys.executable, "-c",
                                                             "raise SystemExit(3)"])
    state = session.state
    with caplog.at_level(logging.WARNING, logger="kuulas.offload"):
        got = offload.call("silence_ranges", state, session.store)
    assert got == analysis.silence_ranges(state, session.store)
    assert any("inline" in r.getMessage() or "worker" in r.getMessage()
               for r in caplog.records)


def test_a_store_the_worker_cannot_reopen_is_measured_inline(process_mode):
    from test_parallel_analysis import three_speakers  # noqa: PLC0415 - shared fixture

    p, store = three_speakers()
    assert offload.call("silence_ranges", p, store) == analysis.silence_ranges(p, store)


def test_only_listed_tasks_run():
    with pytest.raises(KeyError):
        offload.call("os.system", None, None)


def test_the_bundle_hands_the_analysis_worker_its_arguments():
    assert bundle.worker_args(["-m", "kuulas.analysis_worker", "a", "b"]) == ["a", "b"]
    assert bundle.worker_module(["-m", "kuulas.analysis_worker", "a"]) == \
        "kuulas.analysis_worker"
    assert bundle.worker_module(["-m", "kuulas.transcribe_worker", "run", "x"]) == \
        "kuulas.transcribe_worker"
    assert bundle.worker_module(["open", "x"]) is None


def test_selftest_runs_the_analysis_worker_process():
    assert "nice" in selftest.check_analysis_worker()


def test_worker_env_is_not_inherited_priority(process_mode):
    # The editor itself is never lowered by starting a worker.
    before = os.getpriority(os.PRIO_PROCESS, 0)
    offload.probe({"what": "priority"})
    assert os.getpriority(os.PRIO_PROCESS, 0) == before
