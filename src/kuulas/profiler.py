"""A sampling profiler that needs no tools: Help > Record a performance report.

Why it exists: an installed app on a laptop gets slow, and ``py-spy`` needs ``sudo`` and
a developer's machine. This one runs inside the process. While it records, a daemon
thread wakes every ~20 ms, takes ``sys._current_frames()`` (one stack per thread) and
counts: which function each thread is in (*self*), which functions are on its stack
(*inclusive*) and its most common stacks. Off, nothing runs: no thread, no hook.

Cost while on: one dict of frames and a walk over the stacks of the threads that are not
waiting, 50 times a second; it sleeps between samples and holds no lock of the editor
(the session lock is never taken). Stored stacks are capped per thread.

A thread is *waiting* when its innermost frame is in a module that only blocks
(``threading.wait``, ``queue.get``, ``selectors``): such a sample is counted as seen but
not walked. A thread asleep in ``time.sleep`` or a C call shows up under the Python line
that called it, so it can look busy; the report says so.

The report is English plain text next to the log. Paths are shown relative to the home
folder and it holds no project names or transcript text (docs/SECURITY.md): only module
and function names, counts and sizes.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import memory, perf
from .build_info import build_label
from .messages import KuulasError

try:
    import resource
except ImportError:  # Windows: no resource module, so no CPU and peak memory
    resource = None  # type: ignore[assignment]

log = logging.getLogger("kuulas.profiler")

#: Seconds between samples (50 per second).
INTERVAL_S = 0.02
MIN_INTERVAL_S = 0.005
MAX_INTERVAL_S = 1.0
#: Longest recording a request may ask for.
MAX_SECONDS = 3600.0
#: Frames kept of a stack (innermost first) in the "most common stacks".
STACK_DEPTH = 8
#: Frames walked for the inclusive counts.
MAX_WALK = 100
#: Distinct stacks kept per thread; the rest are lumped together.
MAX_STACKS = 2000
OTHER_STACK = ("(other)",)
TOP_FUNCTIONS = 25
TOP_STACKS = 10
#: A thread is listed on its own when it was busy in at least this share of the samples.
BUSY_SHARE = 0.02
MAX_BUSY_THREADS = 10
#: A thread whose innermost frame is in one of these modules is waiting, not working.
WAITING_MODULES = frozenset({
    "threading", "queue", "selectors", "select", "socket", "subprocess",
    "concurrent.futures.thread", "multiprocessing.connection",
    "asyncio.base_events", "asyncio.selector_events", "asyncio.runners",
    "anyio._backends._asyncio", "uvicorn.server", "websockets.legacy.server",
})
#: Home of the report files, relative to the home folder (the log's folder).
REPORT_PATTERN = "performance-%Y%m%d-%H%M%S.txt"


class ProfileRequestError(KuulasError, ValueError):
    """The span or the interval asked for is not one the profiler takes."""


class ProfileBusyError(KuulasError):
    """A recording is already running."""

    def __init__(self) -> None:
        super().__init__("error.profile.busy")


# -- sampling ----------------------------------------------------------------


@dataclass
class ThreadStats:
    name: str
    seen: int = 0
    busy: int = 0
    self_counts: Counter = field(default_factory=Counter)
    inclusive: Counter = field(default_factory=Counter)
    stacks: Counter = field(default_factory=Counter)


@dataclass
class SampleResult:
    ticks: int
    threads: dict[int, ThreadStats]


def _module_of(frame: Any) -> str:
    name = frame.f_globals.get("__name__")
    if isinstance(name, str) and name:
        return name
    return Path(frame.f_code.co_filename).stem  # a name only, never a folder


class Sampler:
    """Counts what ``add`` is given; knows nothing of threads or clocks, so it is tested
    with stand-in frames."""

    def __init__(self, depth: int = STACK_DEPTH, max_stacks: int = MAX_STACKS):
        self.depth = depth
        self.max_stacks = max_stacks
        self.ticks = 0
        self._threads: dict[int, ThreadStats] = {}

    def add(self, frames: Mapping[int, Any], names: Mapping[int, str]) -> None:
        """One sample: ``frames`` ident -> innermost frame, ``names`` ident -> name."""
        self.ticks += 1
        for ident, leaf in frames.items():
            stats = self._threads.get(ident)
            if stats is None:
                stats = self._threads[ident] = ThreadStats(
                    names.get(ident) or f"thread-{ident}")
            stats.seen += 1
            if _module_of(leaf) in WAITING_MODULES:
                continue
            stats.busy += 1
            self._walk(stats, leaf)

    def _walk(self, stats: ThreadStats, leaf: Any) -> None:
        entries: list[str] = []
        functions: set[str] = set()
        frame, walked = leaf, 0
        while frame is not None and walked < MAX_WALK:
            module, name = _module_of(frame), frame.f_code.co_name
            function = f"{module}:{name}"
            if walked == 0:
                stats.self_counts[function] += 1
            functions.add(function)
            if walked < self.depth:
                entries.append(f"{function}:{frame.f_lineno}")
            frame = frame.f_back
            walked += 1
        stats.inclusive.update(functions)
        stack = tuple(entries)
        if stack not in stats.stacks and len(stats.stacks) >= self.max_stacks:
            stack = OTHER_STACK
        stats.stacks[stack] += 1

    def result(self) -> SampleResult:
        return SampleResult(self.ticks, dict(self._threads))


# -- the report --------------------------------------------------------------


def home_relative(text: str, home: Path) -> str:
    """``text`` with the home folder written as ``~`` (a different user's folder with the
    same beginning is left alone)."""
    return re.sub(re.escape(str(home)) + r"(?![\w.-])", "~", text)


def _gib(nbytes: float) -> str:
    return f"{nbytes / 1024**3:.2f} GiB"


def _pct(count: float, ticks: int) -> str:
    return f"{100.0 * count / ticks:5.1f}%" if ticks else "  0.0%"


def helsinki_and_utc(moment: dt.datetime) -> str:
    """``2026-10-20 19:45:03 Helsinki (16:45:03 UTC)`` for an aware ``moment``."""
    utc = moment.astimezone(dt.UTC)
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415 - only here

        local = moment.astimezone(ZoneInfo("Europe/Helsinki"))
    except Exception:  # noqa: BLE001 - no tz database: say UTC only
        return f"{utc:%Y-%m-%d %H:%M:%S} UTC"
    return f"{local:%Y-%m-%d %H:%M:%S} Helsinki ({utc:%H:%M:%S} UTC)"


def _function_table(self_counts: Counter, inclusive: Counter, ticks: int) -> list[str]:
    rows = sorted(inclusive, key=lambda f: (-self_counts[f], -inclusive[f], f))
    lines = ["    self    incl   function"]
    lines += [f"  {_pct(self_counts[f], ticks)} {_pct(inclusive[f], ticks)}   {f}"
              for f in rows[:TOP_FUNCTIONS]]
    return lines


def build_report(*, result: SampleResult, interval: float, wall: float, started: str,
                 build: str, python: str, platform: str,
                 cpu: tuple[float, float] | None, rss: tuple[float | None, float | None],
                 memory: dict[str, Any], facts: list[tuple[str, str]],
                 counters: dict[str, dict[str, float]], home: Path) -> str:
    """The plain-text report. Pure: everything it shows is passed in."""
    ticks = result.ticks
    out = ["Kuulas performance report", "=========================", "",
           f"Build:     {build}", f"Python:    {python}", f"Platform:  {platform}",
           f"Recorded:  {started}",
           f"Span:      {wall:.1f} s, {ticks} samples (asked for one every "
           f"{interval * 1000:.0f} ms; fewer means the program was too busy to be "
           f"sampled that often)"]
    if cpu is not None and wall > 0:
        user, system = cpu
        out.append(f"Process CPU during the span: user {user:.1f} s, system "
                   f"{system:.1f} s = {100 * (user + system) / wall:.0f}% of one core "
                   f"(100% = one core busy all the time)")
    now, peak = rss
    parts = []
    if now is not None:
        parts.append(f"RSS now {_gib(now)}")
    if peak is not None:
        parts.append(f"peak RSS {_gib(peak)}")
    parts.append(f"cache budget {_gib(memory.get('used', 0))} of "
                 f"{_gib(memory.get('limit', 0))}")
    out.append("Memory:    " + ", ".join(parts))
    for kind, s in sorted(memory.get("caches", {}).items()):
        out.append(f"  cache {kind}: {100 * s['hit_rate']:.0f}% hits ({s['hits']} in "
                   f"memory, {s['disk_hits']} from disk, {s['misses']} computed)")
    if facts:
        out += ["", "Engine and project"]
        out += [f"  {label}: {value}" for label, value in facts]
    if counters:
        out += ["", "Counters during the span", "  name  (times, average, largest)"]
        for name, c in sorted(counters.items()):
            out.append(f"  {name}: {c['count']} times, average "
                       f"{c['total'] / c['count']:.3f}, largest {c['max']:.3f}")
    out += ["", "How to read this: a percentage is a share of the samples, so 100% is "
            "one thread in that function for the whole span (the numbers add up to "
            "more than 100% when several threads work at once). \"Busy\" leaves out "
            "threads that were waiting in a lock, queue or select; a thread asleep in "
            "a C call can still look busy under the line that called it.", ""]
    threads = sorted(result.threads.values(), key=lambda s: (-s.busy, s.name))
    out.append(f"Threads ({len(threads)})")
    out.append("   seen    busy   name")
    out += [f"  {_pct(s.seen, ticks)} {_pct(s.busy, ticks)}   {s.name}" for s in threads]
    overall_self: Counter = Counter()
    overall_incl: Counter = Counter()
    for s in threads:
        overall_self.update(s.self_counts)
        overall_incl.update(s.inclusive)
    out += ["", f"Top {TOP_FUNCTIONS} functions overall (busy samples only)"]
    out += _function_table(overall_self, overall_incl, ticks)
    busy = [s for s in threads if ticks and s.busy / ticks >= BUSY_SHARE]
    for s in busy[:MAX_BUSY_THREADS]:
        out += ["", f"== Busy thread: {s.name} (busy {_pct(s.busy, ticks).strip()}) ==",
                f"Top {TOP_FUNCTIONS} functions"]
        out += _function_table(s.self_counts, s.inclusive, ticks)
        out.append("Most common stacks (innermost first, module:function:line)")
        for stack, n in s.stacks.most_common(TOP_STACKS):
            out.append(f"  {_pct(n, ticks)}  " + "  <-  ".join(stack))
    return home_relative("\n".join(out) + "\n", home)


# -- the facts about this process --------------------------------------------


def process_usage() -> tuple[float, float] | None:
    """(user, system) CPU seconds of this process so far."""
    if resource is None:
        return None
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime, r.ru_stime


def process_rss() -> tuple[float | None, float | None]:
    """(resident now, peak resident) in bytes; None where the platform does not say."""
    peak = None
    if resource is not None:
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak = float(raw if sys.platform == "darwin" else raw * 1024)
    now = None
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        now = float(pages * os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError, IndexError):
        try:  # macOS: ps is the one way without a dependency
            done = subprocess.run(  # noqa: S603 - fixed arguments, our own pid
                ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
                capture_output=True, text=True, timeout=3, check=True)
            now = float(done.stdout.strip()) * 1024
        except (OSError, ValueError, subprocess.SubprocessError):
            now = None
    return now, peak


def memory_facts() -> dict[str, Any]:
    return {"used": memory.BUDGET.used, "limit": memory.BUDGET.limit,
            "caches": memory.BUDGET.stats()}


def session_facts(session: Any, engine: Any) -> list[tuple[str, str]]:
    """Engine and project numbers, no names: counts and sizes only. Reads the project
    without taking the session lock (a project is replaced whole, never edited)."""
    facts: list[tuple[str, str]] = []
    try:
        status = engine.status()
        facts += [("Playing", "yes" if status.get("playing") else "no"),
                  ("Late blocks (device underruns)", str(status.get("late_blocks"))),
                  ("Failed blocks", str(status.get("failed_blocks"))),
                  ("Block size / project rate / device rate",
                   f"{status.get('blocksize')} / {status.get('rate')} / "
                   f"{status.get('device_rate')} Hz"),
                  ("Resampling", "yes" if status.get("resampling") else "no")]
    except Exception:
        log.exception("performance report: engine facts failed")
    try:
        project = session.state
        tracks = list(project.tracks)
        clips = sum(len(t.clips) for t in tracks)
        gates = sum(len(t.gate) for t in tracks)
        facts += [("Tracks", str(len(tracks))), ("Clips", str(clips)),
                  ("Gate ranges", str(gates)), ("Media files", str(len(project.media))),
                  ("Buses", str(len(project.buses)))]
        if tracks:
            most = max(len(t.clips) for t in tracks)
            facts.append(("Most clips on one track", str(most)))
    except Exception:
        log.exception("performance report: project facts failed")
    facts.append(("Threads in the process", str(threading.active_count())))
    return facts


def reveal_in_finder(path: Path) -> None:
    """Show the report in Finder (macOS); other systems: nothing."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.Popen(["/usr/bin/open", "-R", str(path)])  # noqa: S603
    except OSError:
        log.warning("could not reveal the performance report in Finder")


def log_folder() -> Path:
    from . import bundle  # noqa: PLC0415 - bundle imports little, but not at import time

    return bundle.log_file(Path.home()).parent


# -- the recording -----------------------------------------------------------


class Profiler:
    """One recording at a time. ``start`` returns at once (a thread does the sampling);
    ``status`` says how it is going; the report is written when the span ends or
    ``stop`` is called."""

    def __init__(self, *, out_dir: Path | None = None,
                 frames: Callable[[], dict] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Any] | None = None,
                 reveal: Callable[[Path], Any] | None = reveal_in_finder,
                 home: Path | None = None,
                 threads: Callable[[], dict[int, str]] | None = None,
                 usage: Callable[[], tuple[float, float] | None] = process_usage,
                 rss: Callable[[], tuple[float | None, float | None]] = process_rss,
                 background: bool = True):
        self._out_dir = out_dir
        self._frames = frames or sys._current_frames
        self._clock = clock
        self._sleep = sleep
        self._reveal = reveal
        self._home = home or Path.home()
        self._threads = threads or (
            lambda: {t.ident: t.name for t in threading.enumerate() if t.ident})
        self._usage, self._rss = usage, rss
        self._background = background
        self._facts: Callable[[], list[tuple[str, str]]] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = {
            "state": "idle", "seconds": 0.0, "interval": INTERVAL_S, "samples": 0,
            "report": None, "error": None}
        self._began = 0.0
        self._sampler: Sampler | None = None

    # -- wiring --

    def set_facts(self, provider: Callable[[], list[tuple[str, str]]] | None) -> None:
        self._facts = provider

    def set_reveal(self, reveal: Callable[[Path], Any] | None) -> None:
        self._reveal = reveal

    # -- control --

    def start(self, seconds: object, interval: float = INTERVAL_S) -> None:
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not 0 < seconds <= MAX_SECONDS):
            raise ProfileRequestError("error.profile.bad_seconds",
                                      max=int(MAX_SECONDS))
        if not MIN_INTERVAL_S <= interval <= MAX_INTERVAL_S:
            raise ProfileRequestError("error.profile.bad_interval",
                                      min=MIN_INTERVAL_S, max=MAX_INTERVAL_S)
        with self._lock:
            if self._state["state"] == "running":
                raise ProfileBusyError
            self._stop = threading.Event()
            self._state = {"state": "running", "seconds": float(seconds),
                           "interval": interval, "samples": 0, "report": None,
                           "error": None}
            self._sampler = Sampler()
            self._began = self._clock()
        if self._background:
            self._thread = threading.Thread(
                target=self._run, args=(float(seconds), interval),
                name="kuulas-profiler", daemon=True)
            self._thread.start()
        else:
            self._run(float(seconds), interval)

    def stop(self) -> None:
        """End the recording now; the report is still written."""
        self._stop.set()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def status(self) -> dict[str, Any]:
        with self._lock:
            out = dict(self._state)
            sampler = self._sampler
        if out["state"] == "running":
            out["elapsed"] = max(0.0, self._clock() - self._began)
            out["samples"] = sampler.ticks if sampler else 0
        return out

    # -- the sampling thread --

    def _run(self, seconds: float, interval: float) -> None:
        sampler = self._sampler
        stop = self._stop
        sleep = self._sleep or stop.wait
        me = threading.get_ident()
        names: dict[int, str] = {}
        try:
            before = perf.COUNTERS.snapshot()
            perf.COUNTERS.reset_max()
            cpu0 = self._usage()
            wall_began = dt.datetime.now(dt.UTC)
            began = self._clock()
            while not stop.is_set() and self._clock() - began < seconds:
                frames = dict(self._frames())
                frames.pop(me, None)
                if sampler.ticks % 25 == 0 or any(i not in names for i in frames):
                    names.update(self._threads())
                sampler.add(frames, names)
                sleep(interval)
            wall = self._clock() - began
            cpu1 = self._usage()
            cpu = (cpu1[0] - cpu0[0], cpu1[1] - cpu0[1]) if cpu0 and cpu1 else None
            path = self._write(sampler, interval, wall, wall_began, cpu,
                               perf.delta(before, perf.COUNTERS.snapshot()))
        except Exception as exc:
            log.exception("performance report failed")
            self._finish({"state": "failed", "error": f"{type(exc).__name__}: {exc}",
                          "samples": sampler.ticks})
            return
        self._finish({"state": "done", "samples": sampler.ticks,
                      "report": home_relative(str(path), self._home)})
        if self._reveal is not None:
            try:
                self._reveal(path)
            except Exception:
                log.exception("could not show the performance report")

    def _finish(self, update: dict[str, Any]) -> None:
        with self._lock:
            self._state.update(update)

    def _write(self, sampler: Sampler, interval: float, wall: float,
               wall_began: dt.datetime, cpu, counters) -> Path:
        facts: list[tuple[str, str]] = []
        if self._facts is not None:
            try:
                facts = list(self._facts())
            except Exception:
                log.exception("performance report: facts failed")
        text = build_report(
            result=sampler.result(), interval=interval, wall=wall,
            started=helsinki_and_utc(wall_began), build=build_label(),
            python=platform.python_version(), platform=platform.platform(), cpu=cpu,
            rss=self._rss(), memory=memory_facts(), facts=facts, counters=counters,
            home=self._home)
        folder = self._out_dir or log_folder()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / wall_began.astimezone().strftime(REPORT_PATTERN)
        n = 1
        while target.exists():
            n += 1
            target = target.with_name(f"{target.stem.split('~')[0]}~{n}.txt")
        target.write_text(text, encoding="utf-8")
        return target


#: The process-wide profiler: the menu, the HTTP endpoint and KUULAS_PROFILE share it.
PROFILER = Profiler()


def start_from_environment(env: Mapping[str, str],
                           profiler: Profiler | None = None) -> bool:
    """``KUULAS_PROFILE=<seconds>`` records from start-up. True when a recording began."""
    raw = env.get("KUULAS_PROFILE", "").strip()
    try:
        seconds = float(raw)
    except ValueError:
        return False
    if not 0 < seconds <= MAX_SECONDS:
        return False
    (profiler or PROFILER).start(seconds)
    return True
