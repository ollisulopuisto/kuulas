"""Jobs carry a message and an indeterminate flag (WP68), for a job whose
progress is not a number (a child process that prints lines)."""

import threading
import time

from kuulas.jobs import Jobs


def wait_state(jobs, job_id, state):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = next(item for item in jobs.list() if item["id"] == job_id)
        if job["state"] == state:
            return job
        time.sleep(0.005)
    raise AssertionError(f"job did not reach {state}: {jobs.list()}")


def test_progress_carries_a_message_and_indeterminate_flag():
    release = threading.Event()
    jobs = Jobs(max_workers=1)

    def work(progress):
        progress(0.4, "loading", indeterminate=True)
        release.wait(2)

    try:
        job_id = jobs.submit("automix", "Mix", work)
        deadline = time.monotonic() + 2
        job = {}
        while time.monotonic() < deadline:
            job = next(item for item in jobs.list() if item["id"] == job_id)
            if job.get("message") == "loading":
                break
            time.sleep(0.005)
        assert job["message"] == "loading"
        assert job["indeterminate"] is True
        assert job["progress"] == 0.4
        release.set()
        done = wait_state(jobs, job_id, "completed")
        assert done["indeterminate"] is False
    finally:
        release.set()
        jobs.close()


def test_jobs_without_a_message_list_empty_defaults():
    jobs = Jobs(max_workers=1)
    try:
        job_id = jobs.submit("test", "Plain", lambda progress: progress(0.5))
        job = wait_state(jobs, job_id, "completed")
        assert job["message"] == ""
        assert job["indeterminate"] is False
    finally:
        jobs.close()
