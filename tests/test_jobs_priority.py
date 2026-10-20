"""Jobs yield to playback (docs/PLAYBACK-PRIORITY.md): a job does not start
while the engine plays, pauses at its next progress call when playback starts,
says so, resumes where it was, and can be cancelled while paused."""

import threading
import time

from kuulas import priority
from kuulas.jobs import JobCancelledError, Jobs
from kuulas.messages import t


def gate_and_switch(playing=False):
    state = {"playing": playing}
    gate = priority.PlaybackGate(hold_s=0.0, poll_s=0.005)
    gate.watch(lambda: state["playing"])
    return gate, state


def job_of(jobs, job_id):
    return next(item for item in jobs.list() if item["id"] == job_id)


def wait_for(predicate, what, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def test_a_job_does_not_start_while_playing():
    gate, state = gate_and_switch(playing=True)
    jobs = Jobs(max_workers=1, gate=gate)
    started = threading.Event()
    try:
        job_id = jobs.submit("test", "Work", lambda _p: started.set())
        time.sleep(0.1)
        assert not started.is_set()
        job = job_of(jobs, job_id)
        assert job["paused"] is True
        assert job["message"] == t("job.paused_playing")
        state["playing"] = False
        wait_for(lambda: job_of(jobs, job_id)["state"] == "completed", "completion")
        assert job_of(jobs, job_id)["paused"] is False
    finally:
        jobs.close()


def test_a_running_job_pauses_at_its_next_progress_and_resumes_where_it_was():
    gate, state = gate_and_switch()
    jobs = Jobs(max_workers=1, gate=gate)
    steps = []
    at_two = threading.Event()

    def work(progress):
        for i in range(5):
            steps.append(i)
            if i == 2:
                at_two.set()
                state["playing"] = True  # playback starts here
            progress((i + 1) / 5, "step")
        return "done"

    try:
        job_id = jobs.submit("test", "Work", work, keep_result=True)
        at_two.wait(2)
        wait_for(lambda: job_of(jobs, job_id)["paused"], "pause")
        time.sleep(0.05)
        assert steps == [0, 1, 2]  # nothing ran while paused
        job = job_of(jobs, job_id)
        assert job["state"] == "running"
        assert job["progress"] == 0.6  # progress kept
        assert job["message"] == t("job.paused_playing")
        assert job["remaining_seconds"] is None
        state["playing"] = False
        wait_for(lambda: job_of(jobs, job_id)["state"] == "completed", "completion")
        assert steps == [0, 1, 2, 3, 4]
        done = job_of(jobs, job_id)
        assert done["result"] == "done"
        assert done["message"] == "step"  # the job's own line is back
    finally:
        jobs.close()


def test_cancel_works_while_paused():
    gate, state = gate_and_switch()
    jobs = Jobs(max_workers=1, gate=gate)
    after = []

    def work(progress):
        state["playing"] = True
        progress(0.5)
        after.append("ran on")

    try:
        job_id = jobs.submit("test", "Work", work)
        wait_for(lambda: job_of(jobs, job_id)["paused"], "pause")
        jobs.cancel(job_id)
        wait_for(lambda: job_of(jobs, job_id)["state"] == "cancelled", "cancel")
        assert after == []
    finally:
        jobs.close()


def test_cancel_of_a_queued_job_waiting_for_playback():
    gate, _ = gate_and_switch(playing=True)
    jobs = Jobs(max_workers=1, gate=gate)
    try:
        job_id = jobs.submit("test", "Work", lambda _p: None)
        wait_for(lambda: job_of(jobs, job_id)["paused"], "pause")
        jobs.cancel(job_id)
        wait_for(lambda: job_of(jobs, job_id)["state"] == "cancelled", "cancel")
    finally:
        jobs.close()


def test_a_chunk_loop_deep_in_a_job_pauses_too():
    """``priority.checkpoint`` in any loop a job calls (analysis, export) pauses
    that job and marks it paused, without a progress call."""
    gate, state = gate_and_switch()
    jobs = Jobs(max_workers=1, gate=gate)
    chunks = []
    paused_seen = threading.Event()

    def work(_progress):
        for i in range(3):
            if i == 1:
                state["playing"] = True
            priority.checkpoint(gate=gate)
            chunks.append(i)

    try:
        job_id = jobs.submit("test", "Work", work)

        def paused():
            if job_of(jobs, job_id)["paused"]:
                paused_seen.set()
                return True
            return False

        wait_for(paused, "pause")
        assert chunks == [0]
        state["playing"] = False
        wait_for(lambda: job_of(jobs, job_id)["state"] == "completed", "completion")
        assert chunks == [0, 1, 2]
    finally:
        jobs.close()


def test_a_cancelled_checkpoint_raises_job_cancelled():
    gate, state = gate_and_switch(playing=True)
    cancel = threading.Event()
    cancel.set()
    with priority.background():
        try:
            priority.checkpoint(cancel, gate=gate)
        except JobCancelledError:
            pass
        else:  # pragma: no cover - the assertion below explains it
            raise AssertionError("checkpoint did not raise on cancel")
    assert state["playing"]


def test_paused_message_is_translated():
    assert t("job.paused_playing") != "job.paused_playing"
