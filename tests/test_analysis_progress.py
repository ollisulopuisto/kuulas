"""An analysis task reports how far it is (owner, 2026-10-24: a progress bar on Level
blocks, the way the podcast tools give structured progress). The task calls ``report``;
in the worker process the report goes through a file, inline through a callback."""

import json
import threading

from kuulas import analysis_progress, offload
from kuulas.model import Project


def test_a_report_without_a_listener_does_nothing(monkeypatch):
    monkeypatch.delenv(analysis_progress.PROGRESS_ENV, raising=False)
    analysis_progress.report(0.5, "tracks", done=1, total=2)  # no error


def test_a_report_goes_to_the_file_the_editor_named(tmp_path, monkeypatch):
    target = tmp_path / "progress.json"
    monkeypatch.setenv(analysis_progress.PROGRESS_ENV, str(target))
    analysis_progress.report(0.25, "tracks", done=1, total=4)
    assert json.loads(target.read_text()) == {
        "fraction": 0.25, "stage": "tracks", "detail": {"done": 1, "total": 4}}


def test_the_editor_reads_what_the_file_says(tmp_path):
    target = tmp_path / "progress.json"
    assert analysis_progress.read(target) is None  # nothing yet
    target.write_text(json.dumps({"fraction": 0.5, "stage": "blocks", "detail": {}}))
    assert analysis_progress.read(target) == (0.5, "blocks", {})
    target.write_text("{not json")
    assert analysis_progress.read(target) is None  # half-written or damaged: skipped


def test_the_fraction_is_kept_between_zero_and_one(tmp_path, monkeypatch):
    target = tmp_path / "progress.json"
    monkeypatch.setenv(analysis_progress.PROGRESS_ENV, str(target))
    analysis_progress.report(7, "x")
    assert analysis_progress.read(target)[0] == 1.0
    analysis_progress.report(-2, "x")
    assert analysis_progress.read(target)[0] == 0.0


def _task_a(project, store, *args, **kwargs):
    analysis_progress.report(0.3, "tracks", done=1, total=3)
    analysis_progress.report(1.0, "blocks")
    return "done"


def _task_b(project, store, *args, **kwargs):
    worker = threading.Thread(
        target=lambda: analysis_progress.report(0.4, "tracks", done=2, total=5))
    worker.start()
    worker.join()
    return 1


def test_an_inline_task_reports_through_the_callback(monkeypatch):
    seen = []
    monkeypatch.setitem(offload.TASKS, "_progress_probe",
                        "test_analysis_progress:_task_a")
    value = offload.call("_progress_probe", Project(), None,
                         on_progress=lambda f, s, d: seen.append((f, s, d)))
    assert value == "done"
    assert seen == [(0.3, "tracks", {"done": 1, "total": 3}), (1.0, "blocks", {})]
    # and it is forgotten afterwards
    analysis_progress.report(0.9, "late")
    assert len(seen) == 2


def test_reports_from_a_pool_thread_reach_the_callback_too(monkeypatch):
    seen = []
    monkeypatch.setitem(offload.TASKS, "_progress_probe",
                        "test_analysis_progress:_task_b")
    offload.call("_progress_probe", Project(), None,
                 on_progress=lambda f, s, d: seen.append((f, s, d)))
    assert seen == [(0.4, "tracks", {"done": 2, "total": 5})]


def test_a_worker_process_reports_through_the_file():
    seen = []
    answer = offload.probe({"what": "report", "steps": 3, "pause": 0.35},
                           on_progress=lambda f, s, d: seen.append((round(f, 2), s, d)))
    assert answer == {"reported": 3}
    assert seen[-1] == (1.0, "step", {"i": 3})
    assert [f for f, _s, _d in seen] == sorted(f for f, _s, _d in seen)
    assert len(seen) >= 2  # at least some were seen while it ran, not only the last
