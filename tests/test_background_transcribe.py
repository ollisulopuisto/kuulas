"""Transcription as a detached background job, the editor side (WP79).

The worker runs inline in a thread here (conftest) with a fake engine: no Colab, no
audio decoding. The detached process itself is tested in test_transcribe_worker.py."""

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import bgjobs, ops
from kuulas.clock import FLICKS
from kuulas.server import create_app
from kuulas.session import Session
from kuulas.transcribe_worker import run_job

RATE = 48000


class Engine:
    def status(self):
        return {"playing": False, "position": 0, "until": None, "notices": []}


def fake_local(path, model="small", language=None, progress=None, **kwargs):
    return [{"w": Path(str(path)).stem, "s": FLICKS // 4, "e": FLICKS // 2, "spk": ""}]


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    monkeypatch.setattr("kuulas.transcribe.local", fake_local)
    monkeypatch.setattr(Session, "BACKGROUND_POLL_S", 0.05)


def build(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    paths = []
    for i, name in enumerate(("Olli", "Maija")):
        audio = (np.random.default_rng(i).standard_normal(RATE) * 0.1).astype(np.float32)
        sf.write(src / f"{name}.wav", audio, RATE, subtype="PCM_16")
        paths.append(str(src / f"{name}.wav"))
    s.import_media(paths)
    return s


@pytest.fixture
def session(tmp_path):
    s = build(tmp_path)
    yield s
    s.close()


def ids(session):
    return [m.id for m in session.state.media]


def wait(check, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        got = check()
        if got:
            return got
        time.sleep(0.02)
    raise AssertionError("condition not reached")


class Holder:
    """Submit but do not run while ``hold``: the test plays the worker itself."""

    hold = True

    def __call__(self, path):
        if not self.hold:
            threading.Thread(target=run_job, args=(path,),
                             kwargs={"status_interval": 0}, daemon=True).start()


def hold_worker(monkeypatch):
    holder = Holder()
    monkeypatch.setattr(bgjobs, "launch_worker", holder)
    return holder


def test_transcribe_writes_a_job_file_in_the_project(session, monkeypatch):
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), "small", "fi", local_engine="orukeet")
    job = bgjobs.read_json(bgjobs.job_file(session.package.path, job_id))
    assert job["backend"] == "local"
    assert job["model"] == "small"
    assert job["language"] == "fi"
    assert job["host"]
    assert [i["id"] for i in job["items"]] == ids(session)
    assert set(job["previous"]) == set(ids(session))
    assert session.background_jobs()[0]["state"] == "queued"


def test_a_finished_transcript_is_added_automatically_with_a_notice(session):
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")

    notices = []

    def finished():
        if len(session.transcripts()) != 2:
            return False
        notices.extend(session.drain_notices())
        return bool(notices)

    wait(finished)
    assert [w["w"] for w in session.transcripts()[ids(session)[0]]] == ["Olli"]
    assert [n["job"] for n in notices] == [job_id]
    assert notices[0]["kind"] == "ok"
    assert "Olli" in notices[0]["text"]
    assert session.drain_notices() == []
    assert not bgjobs.job_file(session.package.path, job_id).exists()  # cleaned up


def test_each_media_is_one_undo_step_and_local_keeps_orukeet_timing(session):
    session.transcribe(ids(session), local_engine="orukeet")
    wait(lambda: len(session.transcripts()) == 2)
    assert {m.timing for m in session.state.media} == {"orukeet"}
    session.undo()
    assert len(session.transcripts()) == 1
    session.undo()
    assert session.transcripts() == {}


def test_a_job_finished_while_closed_is_added_on_open(tmp_path, monkeypatch):
    first = build(tmp_path)
    hold_worker(monkeypatch)
    (job_id,) = first.transcribe(ids(first), local_engine="orukeet")
    folder = first.package.path
    first.close()
    run_job(bgjobs.job_file(folder, job_id), local=fake_local)  # the worker, no editor
    reopened = Session(folder)
    try:
        assert len(reopened.transcripts()) == 2
        assert [n["job"] for n in reopened.drain_notices()] == [job_id]
    finally:
        reopened.close()


def test_a_running_job_is_picked_up_after_reopening(tmp_path, monkeypatch):
    first = build(tmp_path)
    hold_worker(monkeypatch)
    (job_id,) = first.transcribe(ids(first), local_engine="orukeet")
    folder = first.package.path
    first.close()
    reopened = Session(folder)
    try:
        listed = reopened.background_jobs()
        assert [j["id"] for j in listed] == [job_id]
        assert listed[0]["state"] == "queued"
    finally:
        reopened.close()


def test_a_transcript_changed_meanwhile_is_kept_and_the_result_too(session, monkeypatch):
    hold_worker(monkeypatch)
    first, second = ids(session)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    session.set_transcript(first, [{"w": "mine", "s": 0, "e": 5, "spk": ""}], "manual")
    run_job(bgjobs.job_file(session.package.path, job_id), local=fake_local)
    session.poll_background()
    assert session.transcripts()[first][0]["w"] == "mine"
    assert session.transcripts()[second][0]["w"] == "Maija"  # the others still go in
    shown = next(j for j in session.background_jobs() if j["id"] == job_id)
    assert shown["state"] == "failed"
    assert shown["error"]["key"] == "error.transcribe.changed"
    assert bgjobs.result_file(session.package.path, job_id, first).is_file()
    notices = session.drain_notices()
    assert any(n["kind"] == "error" for n in notices)
    session.poll_background()  # not tried again and again
    assert session.transcripts()[first][0]["w"] == "mine"
    assert session.drain_notices() == []


def test_restart_after_a_conflict_replaces_the_newer_transcript(session, monkeypatch):
    holder = hold_worker(monkeypatch)
    first = ids(session)[0]
    (job_id,) = session.transcribe([first], local_engine="orukeet")
    session.set_transcript(first, [{"w": "mine", "s": 0, "e": 5, "spk": ""}], "manual")
    run_job(bgjobs.job_file(session.package.path, job_id), local=fake_local)
    session.poll_background()
    holder.hold = False
    session.restart_background(job_id)
    wait(lambda: session.transcripts()[first][0]["w"] == "Olli")


def test_a_read_only_project_does_not_ingest(session, monkeypatch):
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    run_job(bgjobs.job_file(session.package.path, job_id), local=fake_local)
    monkeypatch.setattr(type(session), "read_only", property(lambda self: True))
    session.poll_background()
    assert session.transcripts() == {}
    assert bgjobs.job_file(session.package.path, job_id).is_file()


# -- several computers ---------------------------------------------------------


def foreign_job(session, state):
    media = ids(session)[0]
    job_id = bgjobs.create_job(
        session.package.path, backend="local",
        items=[{"id": media, "name": "Olli.wav", "path": "/x/Olli.wav"}],
        previous={media: None}, names=["Olli.wav"], model=None, language=None,
        settings=None)
    path = bgjobs.job_file(session.package.path, job_id)
    data = bgjobs.read_json(path)
    bgjobs.write_json_atomic(path, {
        **data, "host": "other-mac.local", "machine": "other-machine"})
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
        "state": state, "progress": 0.4, "pid": 1, "host": "other-mac.local"})
    return job_id, media


def test_another_computers_running_job_is_shown_but_not_run_or_cancelled(session):
    job_id, _ = foreign_job(session, "running")
    shown = session.background_jobs()[0]
    assert shown["foreign"] is True
    assert shown["state"] == "running"  # a pid of another machine says nothing
    with pytest.raises(bgjobs.BackgroundJobError) as e:
        session.cancel_background(job_id)
    assert e.value.key == "error.transcribe.foreign_host"
    with pytest.raises(bgjobs.BackgroundJobError):
        session.restart_background(job_id)
    assert session.transcripts() == {}  # and no ingest while its worker runs


def test_a_result_synced_from_another_computer_is_ingested_here(session):
    job_id, media = foreign_job(session, "completed")
    bgjobs.write_json_atomic(
        bgjobs.result_file(session.package.path, job_id, media),
        bgjobs.words_to_file(fake_local("Olli.wav"), timing="whisper", language="fi"))
    session.poll_background()
    assert session.transcripts()[media][0]["w"] == "Olli"


# -- stale state after a reboot ----------------------------------------------------


def test_a_running_job_from_an_earlier_boot_is_interrupted(session, monkeypatch):
    """A reboot can hand the recorded pid to a live, unrelated process, so a pid
    alone cannot keep a job "running" across boots: the worker's boot token
    decides. The job can then be cancelled, not just shown."""
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    monkeypatch.setattr(bgjobs, "boot_id", lambda: "this-boot")
    alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
            "state": "running", "progress": 0.2, "pid": alive.pid,
            "host": bgjobs._hostname(), "boot": "an-earlier-boot"})
        shown = session.background_jobs()[0]
        assert shown["state"] == "interrupted"
        session.cancel_background(job_id)
        assert session.background_jobs()[0]["state"] == "cancelled"
    finally:
        alive.kill()


def test_a_hostname_spelt_with_a_local_suffix_is_this_computer(session, monkeypatch):
    """macOS reports one Mac as ``name`` and ``name.local`` (and case varies), so
    an exact string compare made the owner's own job "foreign": shown as running
    on his computer and refusing to cancel."""
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    base = re.sub(r"\.local$", "", bgjobs._hostname(), flags=re.IGNORECASE)
    variant = base.upper() + ".LOCAL"
    path = bgjobs.job_file(session.package.path, job_id)
    job = bgjobs.read_json(path)
    bgjobs.write_json_atomic(path, {**job, "host": variant})
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
        "state": "running", "progress": 0.2, "pid": gone.pid, "host": variant})
    shown = session.background_jobs()[0]
    assert shown["foreign"] is False
    assert shown["state"] == "interrupted"
    session.cancel_background(job_id)  # no foreign_host refusal
    assert session.background_jobs()[0]["state"] == "cancelled"


def test_a_legacy_btime_token_falls_back_to_the_pid_check(session, monkeypatch):
    """The first cut of the boot token used /proc/stat btime, a wall clock that
    moves with clock sync; such a token proves nothing, so the pid check decides."""
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    monkeypatch.setattr(bgjobs, "boot_id", lambda: "linux-a-real-uuid")
    alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
            "state": "running", "progress": 0.2, "pid": alive.pid,
            "host": bgjobs._hostname(), "boot": "linux-1794300000"})
        assert session.background_jobs()[0]["state"] == "running"
    finally:
        alive.kill()


def test_a_hostname_collision_does_not_grant_a_foreign_machines_job(session, monkeypatch):
    """Two Macs can collide as ``studio`` and ``studio.local``; when both sides
    record a machine token, that decides, and the other machine's job stays
    foreign even under a normalized hostname."""
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    monkeypatch.setattr(bgjobs, "machine_id", lambda: "machine-a")
    base = re.sub(r"\.local$", "", bgjobs._hostname(), flags=re.IGNORECASE)
    path = bgjobs.job_file(session.package.path, job_id)
    job = bgjobs.read_json(path)
    bgjobs.write_json_atomic(path, {
        **job, "host": base.upper() + ".LOCAL", "machine": "machine-b"})
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
        "state": "running", "progress": 0.2, "pid": 1,
        "host": base.upper() + ".LOCAL"})
    shown = session.background_jobs()[0]
    assert shown["foreign"] is True
    assert shown["state"] == "running"
    with pytest.raises(bgjobs.BackgroundJobError) as e:
        session.cancel_background(job_id)
    assert e.value.key == "error.transcribe.foreign_host"


def test_a_matching_machine_token_keeps_a_hostname_variant_mine(session, monkeypatch):
    """The same Mac under another hostname spelling is still this computer when
    the machine tokens agree; its dead worker reconciles and can be cancelled."""
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    monkeypatch.setattr(bgjobs, "machine_id", lambda: "machine-a")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    base = re.sub(r"\.local$", "", bgjobs._hostname(), flags=re.IGNORECASE)
    variant = base.upper() + ".LOCAL"
    path = bgjobs.job_file(session.package.path, job_id)
    job = bgjobs.read_json(path)
    bgjobs.write_json_atomic(path, {**job, "host": variant, "machine": "machine-a"})
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
        "state": "running", "progress": 0.2, "pid": gone.pid, "host": variant})
    shown = session.background_jobs()[0]
    assert shown["foreign"] is False
    assert shown["state"] == "interrupted"
    session.cancel_background(job_id)
    assert session.background_jobs()[0]["state"] == "cancelled"


def test_an_unreadable_machine_token_means_foreign_not_hostname(session, monkeypatch):
    """A job that names its machine can only be proven ours by a matching token:
    when the local probe fails, the hostname fallback must not hand us control
    (hostnames collide); the job is foreign until the probe recovers."""
    hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    monkeypatch.setattr(bgjobs, "machine_id", lambda: None)
    path = bgjobs.job_file(session.package.path, job_id)
    job = bgjobs.read_json(path)
    bgjobs.write_json_atomic(path, {**job, "machine": "machine-a"})
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
        "state": "running", "progress": 0.2, "pid": 1, "host": bgjobs._hostname()})
    shown = session.background_jobs()[0]
    assert shown["foreign"] is True
    assert shown["state"] == "running"
    with pytest.raises(bgjobs.BackgroundJobError) as e:
        session.cancel_background(job_id)
    assert e.value.key == "error.transcribe.foreign_host"


# -- interrupted, cancel, restart ------------------------------------------------


def interrupted(session, monkeypatch):
    holder = hold_worker(monkeypatch)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id), {
        "state": "running", "progress": 0.2, "pid": gone.pid,
        "host": bgjobs._hostname()})
    return job_id, holder


def test_an_interrupted_job_can_be_restarted(session, monkeypatch):
    job_id, holder = interrupted(session, monkeypatch)
    assert session.background_jobs()[0]["state"] == "interrupted"
    holder.hold = False
    session.restart_background(job_id)
    wait(lambda: len(session.transcripts()) == 2)


def test_cancelling_an_interrupted_job_ends_it_then_dismisses(session, monkeypatch):
    job_id, _ = interrupted(session, monkeypatch)
    session.cancel_background(job_id)
    assert session.background_jobs()[0]["state"] == "cancelled"
    session.cancel_background(job_id)  # on a finished job: dismiss
    assert session.background_jobs() == []
    assert not bgjobs.job_file(session.package.path, job_id).exists()


def test_cancel_stops_a_running_engine_and_stores_nothing(session, monkeypatch):
    def slow(path, model="small", language=None, progress=None, **kwargs):
        progress(0.1)
        wait(lambda: progress.cancelled, 5)
        return fake_local(path)

    monkeypatch.setattr("kuulas.transcribe.local", slow)
    (job_id,) = session.transcribe(ids(session), local_engine="orukeet")
    wait(lambda: session.background_jobs()[0]["state"] == "running")
    session.cancel_background(job_id)
    wait(lambda: session.background_jobs()[0]["state"] == "cancelled")
    assert session.transcripts() == {}


# -- the API ---------------------------------------------------------------------


@pytest.fixture
def client(session, tmp_path):
    with TestClient(create_app(session, Engine(), language="en", ui_dir=tmp_path)) as c:
        yield c


def test_jobs_endpoint_lists_background_jobs_and_drains_notices(session, client):
    r = client.post("/api/transcribe",
                    json={"media_ids": ids(session), "local_engine": "orukeet"})
    (job_id,) = r.json()["jobs"]
    seen = []
    wait(lambda: seen.extend(client.get("/api/jobs/notices").json()["notices"]) or seen)
    assert seen[0]["job"] == job_id
    assert client.get("/api/jobs/notices").json()["notices"] == []
    # The transcript panel polls /api/jobs: it must not swallow the notices.
    assert "notices" not in client.get("/api/jobs").json()


def test_delete_and_restart_endpoints(session, client, monkeypatch):
    job_id, holder = interrupted(session, monkeypatch)
    holder.hold = False
    assert client.post(f"/api/jobs/{job_id}/restart").status_code == 202
    wait(lambda: len(session.transcripts()) == 2)
    assert client.post("/api/jobs/nope/restart").status_code == 404
    assert client.delete("/api/jobs/nope").status_code == 404


def test_restart_all_interrupted(session, client, monkeypatch):
    _, holder = interrupted(session, monkeypatch)
    holder.hold = False
    r = client.post("/api/jobs/restart-interrupted")
    assert len(r.json()["restarted"]) == 1
    wait(lambda: len(session.transcripts()) == 2)


@pytest.mark.parametrize("memory", [None, 8 * 1024**3])
def test_memory_policy_refuses_before_worker_creation(session, monkeypatch, memory):
    from kuulas import local_memory  # noqa: PLC0415
    monkeypatch.setattr(local_memory, "physical_memory", lambda: memory)
    monkeypatch.setattr(session, "_launch_background",
                        lambda *_: pytest.fail("worker launched"))
    with pytest.raises(ops.EditError) as error:
        session.transcribe(ids(session), local_engine="orukeet")
    assert error.value.key == "error.orukeet.memory"
    assert bgjobs.job_ids(session.package.path) == []


def test_memory_override_is_one_job_not_restart_permission(session, monkeypatch):
    from kuulas import local_memory  # noqa: PLC0415
    monkeypatch.setattr(local_memory, "physical_memory", lambda: 8 * 1024**3)
    monkeypatch.setattr(session, "_launch_background", lambda *_: None)
    job_id = session.transcribe(ids(session), allow_low_memory=True,
                                local_engine="orukeet")[0]
    job = bgjobs.read_json(bgjobs.job_file(session.package.path, job_id))
    assert job["allow_low_memory"] is True
    status = bgjobs.read_json(bgjobs.status_file(session.package.path, job_id))
    bgjobs.write_json_atomic(bgjobs.status_file(session.package.path, job_id),
                            {**status, "state": "failed"})
    with pytest.raises(ops.EditError) as error:
        session.restart_background(job_id)
    assert error.value.key == "error.orukeet.memory"
