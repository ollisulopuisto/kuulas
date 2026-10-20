"""The built-in sampling profiler (Help > Record a performance report).

Fakes only: frames are stand-ins with the four attributes the sampler reads, the clock
and the sleep are injected, nothing plays.
"""

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from kuulas import perf, profiler

HOME = Path("/Users/someone")


def frame(module, function, line, parent=None):
    """A stand-in for a frame object: leaf-first chains through ``f_back``."""
    return SimpleNamespace(
        f_code=SimpleNamespace(co_name=function, co_filename=f"{HOME}/proj/{module}.py"),
        f_lineno=line, f_globals={"__name__": module}, f_back=parent)


def chain(*calls):
    """``chain(("a","main",1), ("b","work",2))``: root first; returns the leaf frame."""
    leaf = None
    for module, function, line in calls:
        leaf = frame(module, function, line, leaf)
    return leaf


# -- the aggregator ----------------------------------------------------------


def test_self_and_inclusive_counts():
    sampler = profiler.Sampler()
    leaf = chain(("kuulas.engine", "_render", 10), ("kuulas.mixer", "mix", 20),
                 ("kuulas.mixer", "_track", 30))
    for _ in range(4):
        sampler.add({1: leaf}, {1: "kuulas-engine"})
    result = sampler.result()
    assert result.ticks == 4
    thread = result.threads[1]
    assert thread.name == "kuulas-engine"
    assert thread.busy == 4
    assert thread.self_counts["kuulas.mixer:_track"] == 4
    assert thread.inclusive["kuulas.engine:_render"] == 4
    assert thread.inclusive["kuulas.mixer:mix"] == 4
    assert "kuulas.engine:_render" not in thread.self_counts


def test_recursion_counts_a_function_once_per_sample():
    sampler = profiler.Sampler()
    leaf = chain(("m", "f", 1), ("m", "f", 1), ("m", "f", 1))
    sampler.add({1: leaf}, {1: "t"})
    assert sampler.result().threads[1].inclusive["m:f"] == 1


def test_stacks_are_cut_to_the_depth_and_keep_the_leaf_end():
    sampler = profiler.Sampler(depth=3)
    leaf = chain(*[("m", f"f{i}", i) for i in range(10)])
    sampler.add({1: leaf}, {1: "t"})
    (stack,) = sampler.result().threads[1].stacks
    assert [entry.split(":")[1] for entry in stack] == ["f9", "f8", "f7"]
    assert stack[0] == "m:f9:9"


def test_waiting_threads_are_not_busy():
    sampler = profiler.Sampler()
    waiting = chain(("kuulas.engine", "_helper", 5), ("threading", "wait", 300))
    busy = chain(("kuulas.engine", "_render", 5))
    for _ in range(3):
        sampler.add({1: waiting, 2: busy}, {1: "idle", 2: "hot"})
    result = sampler.result()
    assert result.threads[1].busy == 0
    assert result.threads[1].seen == 3
    assert result.threads[2].busy == 3


def test_stored_stacks_are_capped():
    sampler = profiler.Sampler(max_stacks=5)
    for i in range(50):
        sampler.add({1: chain(("m", f"f{i}", i))}, {1: "t"})
    thread = sampler.result().threads[1]
    assert len(thread.stacks) <= 6  # five distinct + the "(other)" bucket
    assert sum(thread.stacks.values()) == 50


def test_unnamed_threads_get_an_identifier_name():
    sampler = profiler.Sampler()
    sampler.add({77: chain(("m", "f", 1))}, {})
    assert sampler.result().threads[77].name == "thread-77"


# -- the report --------------------------------------------------------------


def make_result():
    sampler = profiler.Sampler()
    hot = chain(("kuulas.engine", "_render", 10), ("kuulas.mixer", "mix", 20),
                ("kuulas.mixer", "_mute_ramps", 30))
    cold = chain(("threading", "wait", 1))
    for _ in range(10):
        sampler.add({1: hot, 2: cold}, {1: "kuulas-engine", 2: "kuulas-bgjobs"})
    return sampler.result()


def make_report(**overrides):
    args = {
        "result": make_result(), "interval": 0.02, "wall": 30.0,
        "started": "2026-10-20 19:45:03 Helsinki (16:45:03 UTC)",
        "build": "v26.10.20.1+abc1234", "python": "3.14.0", "platform": "macOS-15",
        "cpu": (20.0, 1.5), "rss": (2 * 1024**3, 3 * 1024**3),
        "memory": {"used": 1024**3, "limit": 2 * 1024**3,
                   "caches": {"peaks": {"hits": 9, "disk_hits": 0, "misses": 1,
                                        "hit_rate": 0.9}}},
        "facts": [("Playing", "yes"), ("Clips", "812")],
        "counters": {"engine.mix_ms": {"count": 100, "total": 500.0, "max": 40.0}},
        "home": HOME,
    }
    args.update(overrides)
    return profiler.build_report(**args)


def test_report_has_the_required_sections():
    text = make_report()
    for needle in ("v26.10.20.1+abc1234", "Python:    3.14.0", "macOS-15", "10 samples",
                   "30.0 s", "Helsinki", "UTC", "kuulas-engine", "kuulas-bgjobs",
                   "Top 25 functions", "Most common stacks", "Playing", "Clips",
                   "engine.mix_ms", "RSS", "peaks", "user 20.0 s"):
        assert needle in text, needle


def test_report_ranks_the_hot_function_first_with_percentages():
    text = make_report()
    section = text.split("Top 25 functions overall")[1]
    first = next(line for line in section.splitlines() if "kuulas.mixer" in line)
    assert "_mute_ramps" in first
    assert "100.0%" in first


def test_report_names_waiting_threads_as_waiting():
    text = make_report()
    line = next(line for line in text.splitlines() if "kuulas-bgjobs" in line)
    assert "0.0%" in line  # busy share


def test_report_leaves_the_home_folder_out():
    text = make_report(facts=[("Folder", f"{HOME}/Documents/x")])
    assert str(HOME) not in text
    assert "~/Documents/x" in text


def test_home_relative_replaces_only_the_home_prefix():
    assert profiler.home_relative(f"{HOME}/a/b", HOME) == "~/a/b"
    assert profiler.home_relative(f"x {HOME}/a and {HOME}", HOME) == "x ~/a and ~"
    assert profiler.home_relative("/Users/someoneelse/a", HOME) == "/Users/someoneelse/a"


def test_top_functions_are_capped_at_25():
    sampler = profiler.Sampler()
    for i in range(40):
        sampler.add({1: chain(("m", f"f{i}", i))}, {1: "t"})
    text = make_report(result=sampler.result())
    section = text.split("Top 25 functions overall")[1].split("== Busy thread")[0]
    assert section.count("m:f") <= 25


# -- the controller -----------------------------------------------------------


class FakeFrames:
    """``sys._current_frames`` returning the same leaf for two fake threads."""

    def __init__(self):
        self.leaf = chain(("kuulas.engine", "_render", 10))

    def __call__(self):
        return {1: self.leaf, 2: self.leaf}


def make_profiler(tmp_path, **kw):
    clock = {"now": 0.0}

    def sleep(seconds):
        clock["now"] += seconds

    args = {"out_dir": tmp_path, "frames": FakeFrames(), "clock": lambda: clock["now"],
            "sleep": sleep, "reveal": lambda _path: None, "home": HOME,
            "threads": lambda: {1: "kuulas-engine", 2: "other"},
            "usage": lambda: (1.0, 0.5), "rss": lambda: (1024**3, 2 * 1024**3),
            "background": False}
    args.update(kw)
    return profiler.Profiler(**args)


def test_a_run_samples_for_the_span_and_writes_a_report(tmp_path):
    revealed = []
    p = make_profiler(tmp_path, reveal=revealed.append)
    p.start(1.0)
    p.join()
    status = p.status()
    assert status["state"] == "done"
    assert status["samples"] == pytest.approx(50, abs=2)  # 1.0 s at 20 ms
    reports = list(tmp_path.glob("performance-*.txt"))
    assert len(reports) == 1
    assert revealed == [reports[0]]
    assert status["report"].startswith("~") or status["report"].endswith(reports[0].name)
    assert "kuulas-engine" in reports[0].read_text(encoding="utf-8")


def test_interval_is_configurable(tmp_path):
    p = make_profiler(tmp_path)
    p.start(1.0, interval=0.1)
    p.join()
    assert p.status()["samples"] == pytest.approx(10, abs=1)


def test_one_report_at_a_time(tmp_path):
    gate = threading.Event()
    p = make_profiler(tmp_path, sleep=lambda _s: gate.wait(5), background=True)
    p.start(10.0)
    try:
        with pytest.raises(profiler.ProfileBusyError):
            p.start(10.0)
        assert p.status()["state"] == "running"
    finally:
        gate.set()
        p.stop()
        p.join()


def test_stop_ends_early_but_still_reports(tmp_path):
    ticks = {"n": 0}
    holder = {}

    def sleep(_seconds):
        ticks["n"] += 1
        if ticks["n"] == 5:
            holder["p"].stop()

    p = make_profiler(tmp_path, sleep=sleep)
    holder["p"] = p
    p.start(30.0)
    p.join()
    assert p.status()["state"] == "done"
    assert p.status()["samples"] < 10
    assert list(tmp_path.glob("performance-*.txt"))


def test_seconds_are_validated(tmp_path):
    p = make_profiler(tmp_path)
    for bad in (0, -5, 3601, "x", None):
        with pytest.raises(ValueError, match="seconds"):
            p.start(bad)
    with pytest.raises(ValueError, match="interval"):
        p.start(10, interval=0.0001)


def test_a_failing_report_is_a_failed_state_not_a_crash(tmp_path):
    p = make_profiler(tmp_path, out_dir=tmp_path / "missing" / "file")
    (tmp_path / "missing").write_text("a file, so the folder cannot be made")
    p.start(0.1)
    p.join()
    assert p.status()["state"] == "failed"
    assert p.status()["error"]


def test_facts_provider_lines_end_up_in_the_report(tmp_path):
    p = make_profiler(tmp_path)
    p.set_facts(lambda: [("Tracks", "4")])
    p.start(0.1)
    p.join()
    (report,) = tmp_path.glob("performance-*.txt")
    assert "Tracks" in report.read_text(encoding="utf-8")


def test_a_failing_facts_provider_does_not_lose_the_report(tmp_path):
    def broken():
        raise RuntimeError("boom")

    p = make_profiler(tmp_path)
    p.set_facts(broken)
    p.start(0.1)
    p.join()
    assert p.status()["state"] == "done"


def test_counters_are_reported_as_a_delta_over_the_span(tmp_path):
    perf.COUNTERS.note("test.before", 5.0)
    now = [0.0]

    def sleep(seconds):
        if now[0] == 0.0:
            perf.COUNTERS.note("test.during", 7.0)
        now[0] += seconds

    p = make_profiler(tmp_path, sleep=sleep, clock=lambda: now[0])
    p.start(0.1)
    p.join()
    (report,) = tmp_path.glob("performance-*.txt")
    text = report.read_text(encoding="utf-8")
    assert "test.during" in text
    assert "test.before" not in text


def test_the_profiler_does_not_sample_itself(tmp_path):
    seen = {}

    def frames():
        seen["ident"] = threading.get_ident()
        return {threading.get_ident(): chain(("m", "f", 1))}

    p = make_profiler(tmp_path, frames=frames)
    p.start(0.1)
    p.join()
    assert p.status()["samples"] > 0
    (report,) = tmp_path.glob("performance-*.txt")
    assert "m:f" not in report.read_text(encoding="utf-8")


def test_environment_start(tmp_path):
    p = make_profiler(tmp_path)
    assert profiler.start_from_environment({}, p) is False
    assert profiler.start_from_environment({"KUULAS_PROFILE": "nonsense"}, p) is False
    assert profiler.start_from_environment({"KUULAS_PROFILE": "0"}, p) is False
    assert profiler.start_from_environment({"KUULAS_PROFILE": "1"}, p) is True
    p.join()
    assert p.status()["state"] == "done"


def test_idle_costs_no_thread(tmp_path):
    before = threading.active_count()
    p = make_profiler(tmp_path, background=True)
    assert threading.active_count() == before
    assert p.status()["state"] == "idle"


# -- the real thing, once ------------------------------------------------------


def test_the_real_sampler_sees_a_busy_thread(tmp_path):
    stop = threading.Event()

    def spin():
        while not stop.is_set():
            sum(range(1000))

    worker = threading.Thread(target=spin, name="kuulas-test-spin", daemon=True)
    worker.start()
    p = profiler.Profiler(out_dir=tmp_path, reveal=lambda _p: None)
    try:
        p.start(0.3, interval=0.01)
        p.join()
    finally:
        stop.set()
        worker.join()
    (report,) = tmp_path.glob("performance-*.txt")
    text = report.read_text(encoding="utf-8")
    assert "kuulas-test-spin" in text
    assert "spin" in text
