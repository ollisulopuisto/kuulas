import threading
import time

from kuulas.jobs import JobCancelledError, Jobs


def wait_state(jobs, job_id, state):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        job = next(item for item in jobs.list() if item["id"] == job_id)
        if job["state"] == state:
            return job
        time.sleep(0.005)
    raise AssertionError(f"job did not reach {state}: {jobs.list()}")


def test_progress_completion_and_callback():
    completed = []
    jobs = Jobs(max_workers=1)
    try:
        job_id = jobs.submit("transcribe", "Speech", lambda progress: (
            progress(0.4), "words")[-1], completed.append)
        job = wait_state(jobs, job_id, "completed")
        assert job["progress"] == 1
        assert completed == ["words"]
    finally:
        jobs.close()


def test_errors_are_captured_without_escaping_worker():
    jobs = Jobs(max_workers=1)
    try:
        job_id = jobs.submit("test", "Broken", lambda _progress: 1 / 0)
        job = wait_state(jobs, job_id, "failed")
        assert job["error"]["key"] == "error.job.failed"
        assert "ZeroDivisionError" in job["error"]["text"]
    finally:
        jobs.close()


def test_running_job_can_be_cancelled_cooperatively():
    started = threading.Event()
    jobs = Jobs(max_workers=1)

    def work(progress):
        started.set()
        while not progress.cancelled:
            time.sleep(0.002)
        raise JobCancelledError

    try:
        job_id = jobs.submit("test", "Cancelable", work)
        assert started.wait(1)
        jobs.cancel(job_id)
        assert wait_state(jobs, job_id, "cancelled")["state"] == "cancelled"
    finally:
        jobs.close()


def test_jobs_run_in_parallel():
    barrier = threading.Barrier(2)
    jobs = Jobs(max_workers=2)

    def work(_progress):
        barrier.wait(timeout=1)
        return True

    try:
        ids = [jobs.submit("test", "Parallel", work) for _ in range(2)]
        assert all(wait_state(jobs, job_id, "completed") for job_id in ids)
    finally:
        jobs.close()


def test_interactive_mode_yields_chunks_to_one_worker():
    lock = threading.Lock()
    active = maximum = 0
    jobs = Jobs(max_workers=3)
    jobs.set_interactive(True)

    def work(progress):
        nonlocal active, maximum
        for step in range(8):
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.002)
            with lock:
                active -= 1
            progress((step + 1) / 8)

    try:
        ids = [jobs.submit("test", "Yielding", work) for _ in range(3)]
        assert all(wait_state(jobs, job_id, "completed") for job_id in ids)
        assert maximum == 1
    finally:
        jobs.close()
