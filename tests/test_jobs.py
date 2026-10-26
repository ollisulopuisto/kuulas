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


# -- a long session: finished jobs do not pile up --------------------------------------
# Every Auto-Silence preview, level measure, export and automix is a job. Before, each
# stayed listed for the life of the process, with its result and its closure (the
# project snapshot it measured). ``list`` (the live channel calls it every 0.25 s, and
# 30 times a second while playing) and every "jobs" message carried all of them.


def wait_all_finished(jobs, ids):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        states = {item["id"]: item["state"] for item in jobs.list()}
        if all(states.get(i, "gone") != "queued" and states.get(i, "gone") != "running"
               for i in ids):
            return
        time.sleep(0.005)
    raise AssertionError("jobs did not finish")


def test_finished_jobs_are_kept_only_up_to_a_bound():
    from kuulas import jobs as jobsm  # noqa: PLC0415 - the bound under test

    # One worker: the jobs end in the order they were submitted. The bound drops the
    # oldest to have *ended*, so with two workers the first job can end late and be kept.
    jobs = Jobs(max_workers=1)
    try:
        ids = [jobs.submit("measure", "Measure", lambda _p, i=i: [i] * 1000,
                           keep_result=True) for i in range(jobsm.FINISHED_KEPT * 4)]
        wait_all_finished(jobs, ids)
        listed = jobs.list()
        assert len(listed) == jobsm.FINISHED_KEPT
        # The newest are the ones kept: the UI polls the job it just started.
        newest = next(j for j in listed if j["id"] == ids[-1])
        assert newest["result"][0] == len(ids) - 1
        assert ids[0] not in {j["id"] for j in listed}
    finally:
        jobs.close()


def test_running_and_queued_jobs_are_never_dropped():
    from kuulas import jobs as jobsm  # noqa: PLC0415 - the bound under test

    release = threading.Event()
    jobs = Jobs(max_workers=1)
    try:
        slow = jobs.submit("export", "Export", lambda _p: release.wait(5))
        wait_state(jobs, slow, "running")
        waiting = jobs.submit("export", "Queued", lambda _p: None)
        quick = []
        for _ in range(jobsm.FINISHED_KEPT + 5):
            quick.append(jobs.submit("x", "x", lambda _p: None))
            jobs.cancel(quick[-1])  # queued behind the slow one: cancelled at once
        ids = {j["id"] for j in jobs.list()}
        assert slow in ids
        assert waiting in ids
        release.set()
        wait_state(jobs, waiting, "completed")
    finally:
        release.set()
        jobs.close()


def test_a_finished_job_lets_go_of_what_its_work_captured():
    import gc  # noqa: PLC0415
    import weakref  # noqa: PLC0415

    class Snapshot:
        pass

    jobs = Jobs(max_workers=1)
    try:
        snap = Snapshot()
        ref = weakref.ref(snap)
        job_id = jobs.submit("measure", "Measure", lambda _p, s=snap: id(s))
        del snap
        wait_state(jobs, job_id, "completed")
        gc.collect()
        assert ref() is None, "the finished job still holds its closure"
    finally:
        jobs.close()
