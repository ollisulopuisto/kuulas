"""The automix toast's structured detail (docs/design/TOAST.md): the job's ``detail``
says which phase, track and stage, so the UI does not have to parse the text line.

The text (``message``) stays exactly as before; ``detail`` is extra and JSON-friendly."""

import json
import threading
import time

from test_automix import Reports, fake, session  # noqa: F401 (fixtures)
from test_automix_events import tool  # noqa: F401 (fixture)
from test_automix_remote import remote, temp_root  # noqa: F401 (fixtures)

from kuulas import automix, messages
from kuulas.jobs import Jobs


def wait(jobs, timeout=10):
    deadline = time.monotonic() + timeout
    while (jobs.list()[0]["state"] in {"queued", "running"}
           and time.monotonic() < deadline):
        time.sleep(0.01)
    return jobs.list()[0]


# -- the job field ---------------------------------------------------------------------

def test_detail_is_null_until_set_and_null_again_when_done():
    jobs = Jobs(max_workers=1)
    seen = {}

    def work(progress):
        seen["first"] = jobs.list()[0]["detail"]
        progress.set_detail({"phase": 1, "phases": 4, "phase_name": "stems",
                             "track": None, "stage": None})
        seen["later"] = jobs.list()[0]["detail"]

    jobs.submit("automix", "t", work)
    job = wait(jobs)
    jobs.close()
    assert seen["first"] is None
    assert seen["later"]["phase_name"] == "stems"
    assert job["state"] == "completed"
    assert job["detail"] is None


def test_detail_is_null_after_a_failure():
    jobs = Jobs(max_workers=1)

    def work(progress):
        progress.set_detail({"phase": 3, "phases": 4, "phase_name": "tracks",
                             "track": None, "stage": None})
        raise RuntimeError("boom")

    jobs.submit("automix", "t", work)
    job = wait(jobs)
    jobs.close()
    assert job["state"] == "failed"
    assert job["detail"] is None


# -- StepTracker.detail ----------------------------------------------------------------

def test_tracker_detail_follows_the_phases():
    messages.set_language("en")
    steps = automix.StepTracker(["Olli", "Maija"])
    steps.stems("Olli 1/2")
    assert steps.detail() == {"phase": 1, "phases": 4, "phase_name": "stems",
                              "track": None, "stage": None}
    steps.label("loading 2 tracks")
    assert steps.detail()["phase_name"] == "analysis"
    assert steps.detail()["phase"] == 2


def test_a_stage_text_line_is_a_done_stage_of_a_track():
    steps = automix.StepTracker(["Olli", "Maija"], {"speech_debleed": True})
    message = steps.label("Maija: debleed")
    assert "track 2/2 Maija" in message  # the text is as before
    detail = steps.detail()
    assert detail["phase"] == 3
    assert detail["phase_name"] == "tracks"
    assert detail["track"] == {"index": 2, "total": 2, "name": "Maija"}
    assert detail["stage"]["name"] == "debleed"
    assert detail["stage"]["n"] == 2
    assert detail["stage"]["of"] == 9
    assert detail["stage"]["state"] == "done"


def test_a_stage_event_says_working_and_lists_the_stages_that_are_off():
    steps = automix.StepTracker(["Olli"], {"speech_plugins": []})
    steps.event({"event": "stage", "track": "Olli", "stage": "cleanup",
                 "state": "start"})
    stage = steps.detail()["stage"]
    assert stage["name"] == "cleanup"
    assert stage["state"] == "working"
    assert "plugin" in stage["off"]  # no plug-ins chosen: the stage is skipped
    assert "read" not in stage["off"]
    steps.event({"event": "stage", "track": "Olli", "stage": "duck", "state": "skipped"})
    assert steps.detail()["stage"]["state"] == "skipped"


def test_mastering_clears_the_track_and_stage():
    steps = automix.StepTracker(["Olli"])
    steps.label("Olli: write")
    steps.label("Engine: mastering the mix")
    assert steps.detail() == {"phase": 4, "phases": 4, "phase_name": "mastering",
                              "track": None, "stage": None}


def test_a_remote_run_has_six_phases():
    steps = automix.StepTracker([], remote=True)
    steps.upload("Olli.wav")
    assert steps.detail()["phase"] == 2
    assert steps.detail()["phases"] == 6
    assert steps.detail()["phase_name"] == "upload"
    steps.download()
    assert steps.detail()["phase"] == 6
    assert steps.detail()["phase_name"] == "download"


# -- automix.run ------------------------------------------------------------------------

def run_details(session, settings):  # noqa: F811
    details, reports = [], Reports()
    automix.run(session, {}, settings, reports, threading.Event(), detail=details.append)
    return details, reports


def test_run_reports_the_stems_first_and_json_only(session, fake):  # noqa: F811
    details, _reports = run_details(session, fake)
    assert details[0]["phase_name"] == "stems"
    json.dumps(details)  # never raises: plain data only


def test_run_follows_the_stage_events(session, tool, temp_root):  # noqa: F811
    details, _reports = run_details(session, tool)
    working = [d for d in details
               if d and d["stage"] and d["stage"]["state"] == "working"]
    assert working
    assert working[-1]["stage"]["name"] == "plugin"
    assert working[-1]["track"]["name"] == "Olli"
    assert working[-1]["phase_name"] == "tracks"


def test_run_keeps_the_text_as_it_was(session, tool, temp_root):  # noqa: F811
    _details, with_detail = run_details(session, tool)
    plain = Reports()
    automix.run(session, {}, tool, plain, threading.Event())
    assert [m for _f, m, _i in with_detail.items] == [m for _f, m, _i in plain.items]


def test_a_remote_run_reports_upload_and_download(session, remote, temp_root):  # noqa: F811
    details, _reports = run_details(session, {"remote": remote["remote"]})
    names = [d["phase_name"] for d in details]
    assert "upload" in names
    assert "download" in names
    assert all(d["phases"] == 6 for d in details)


def test_the_session_job_lists_the_detail(session, monkeypatch):  # noqa: F811
    seen = {}

    def fake_run(_session, _params, _settings, _report, _cancel, **kw):
        kw["detail"]({"phase": 2, "phases": 4, "phase_name": "analysis",
                      "track": None, "stage": None})
        seen["listed"] = session.jobs.list()[0]["detail"]
        return {"path": str(session.package.path), "log_file": None}

    monkeypatch.setattr(automix, "run", fake_run)
    monkeypatch.setattr(automix, "load_settings", dict)
    [job_id] = session.automix({})
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = next(j for j in session.jobs.list() if j["id"] == job_id)
        if job["state"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert seen["listed"]["phase_name"] == "analysis"
    assert job["detail"] is None
