"""Time left in the automix toast: sampler wiring in ``automix.run`` and the job field.

The fake automixer is the one of ``test_automix``; the clock is fake (each call moves
it on)."""

import threading
import time
from pathlib import Path

from test_automix import Reports, fake, session  # noqa: F401 (fixtures)
from test_automix_remote import remote, temp_root  # noqa: F401 (fixtures)

from kuulas import automix, messages
from kuulas.jobs import Jobs


class Clock:
    """A fake clock: each call moves it on by ``step`` seconds."""

    def __init__(self, step=10.0):
        self.now = 1000.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def progress_runner(percents, etas=None):
    def runner(cmd, _cwd, on_line, _cancel):
        assert not etas  # nothing came from the stems export
        for pct in percents:
            on_line(f"PROGRESS {pct} step")
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
        return 0
    return runner


def test_none_early_then_a_json_list(session, fake):  # noqa: F811
    etas = []
    automix.run(session, {}, fake, Reports(), threading.Event(),
                run_process=progress_runner((10, 20, 30, 40, 50), etas),
                eta=etas.append, clock=Clock())
    assert etas[0] is None
    assert etas[1] is None  # fewer than three samples
    assert etas[2] is not None
    assert isinstance(etas[-1], list)
    assert etas[-1][0] in {"under_minute", "minutes", "hours_minutes"}


def test_hours_minutes_is_a_nested_list(session, fake):  # noqa: F811
    etas = []
    automix.run(session, {}, fake, Reports(), threading.Event(),
                run_process=progress_runner((10, 11, 12)),
                eta=etas.append, clock=Clock(step=600.0))
    assert etas[-1][0] == "hours_minutes"
    assert isinstance(etas[-1][1], list)


def test_never_negative(session, fake):  # noqa: F811
    etas = []
    automix.run(session, {}, fake, Reports(), threading.Event(),
                run_process=progress_runner((10, 50, 90, 100)),
                eta=etas.append, clock=Clock())
    assert all(e is None or e[0] != "minutes" or e[1] >= 0 for e in etas)


def test_without_a_callback_nothing_changes(session, fake):  # noqa: F811
    result = automix.run(session, {}, fake, Reports(), threading.Event())
    assert Path(result["path"]).is_file()


def test_a_remote_run_estimates_only_in_its_automixer_phase(
        session, remote, temp_root):  # noqa: F811
    etas = []
    automix.run(session, {}, {"remote": remote["remote"]}, Reports(), threading.Event(),
                eta=etas.append, clock=Clock())
    # the fake automixer prints PROGRESS 25, 10, 50, 75, 100: one call each, none for
    # the stems, the upload or the download
    assert len(etas) == 5
    assert etas[:3] == [None, None, None]  # two samples grew so far
    assert etas[3] is not None


def test_the_job_lists_the_eta():
    messages.set_language("en")
    jobs = Jobs(max_workers=1)
    seen = {}

    def work(progress):
        seen["first"] = jobs.list()[0]["eta"]
        progress.set_eta(["minutes", 12])
        seen["later"] = jobs.list()[0]["eta"]

    jobs.submit("automix", "t", work)
    deadline = time.monotonic() + 10
    while jobs.list()[0]["state"] != "completed" and time.monotonic() < deadline:
        time.sleep(0.01)
    jobs.close()
    assert seen == {"first": None, "later": ["minutes", 12]}
    assert jobs.list()[0]["eta"] is None  # done: no estimate left
