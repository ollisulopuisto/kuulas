"""Playback first: background work yields to the audio (docs/PLAYBACK-PRIORITY.md).

Owner rule (2026-10-20): background processing must never compete with
playback; only the recorder (its own process) outranks it. A ``sample`` of the
app during choppy playback showed two worker threads busy in numpy, scipy and
libsndfile while the PortAudio callback waited ~130 samples for the GIL. One
GIL means any Python work in the editor process delays the callback, however
many cores are idle. So:

* ``GATE`` (``PlaybackGate``) knows whether the engine plays. It reads the
  engine's ``is_playing`` flag (a plain attribute: no lock the audio thread
  takes), and holds for ``HOLD_S`` after playback, a scrub, or input while
  playing, so a stop-start or a drag does not let a chunk in between.
* Background threads are *marked* (``background()``, ``executor``,
  ``gated_map``, ``thread``, and every ``Jobs`` worker). ``checkpoint()``,
  called between chunks of every heavy loop, waits while the gate says
  playing - on a marked thread only. A request thread the UI waits on is never
  paused (it may hold the session lock), so a chunk loop can call
  ``checkpoint()`` without knowing who called it.
* ``gated_map`` replaces a thread pool: while playing, a background caller
  starts no new item; while the user is interacting (playing, or input in the
  last ``INTERACTIVE_S``) at most one item runs at a time.
* Marked threads ask the OS for a lower QoS class (``lower_this_thread``).
  Utility, not background: a thread at background QoS that holds the GIL on an
  efficiency core would make the audio thread wait longer, not shorter. The
  analysis worker *process* (``offload``) has its own GIL and runs at nice 10
  (``lower_this_process``; nice 19 with the Darwin background band starved it).
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import logging
import math
import os
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("kuulas.priority")

#: After playback stops, a scrub, or input while playing, background work stays
#: paused this long (owner, 2026-10-20: "pause for 1 s after the last input").
HOLD_S = 1.0
#: Input this recent counts as interacting: background pools drop to one worker.
#: The live loop's old heuristic (``Jobs.set_interactive``) used the same 2 s.
INTERACTIVE_S = 2.0
#: How often a paused thread looks again. 50 ms: resumes within a blink, and a
#: paused thread wakes 20 times a second for one attribute read.
POLL_S = 0.05


class CancelledError(Exception):
    """Cooperative cancellation (``jobs.JobCancelledError`` is this class)."""


class PlaybackGate:
    """Is the engine playing? ``clock`` and ``sleep`` are injectable for tests."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] | None = None,
                 hold_s: float = HOLD_S, interactive_s: float = INTERACTIVE_S,
                 poll_s: float = POLL_S):
        self._clock = clock
        self._sleep = sleep
        self.hold_s = hold_s
        self.interactive_s = interactive_s
        self.poll_s = poll_s
        self.reset()

    def reset(self) -> None:
        """Forget the source and every timestamp (a test starts clean)."""
        self._source: Callable[[], bool] | None = None
        # Plain floats replaced whole: read and written without a lock, so a
        # caller never waits on another to learn whether audio plays.
        self._hold_until = -math.inf
        self._last_input = -math.inf

    def watch(self, source: Callable[[], bool] | None) -> None:
        """Follow ``source()`` (the engine's ``is_playing``); None stops."""
        self._source = source

    def _playing_now(self) -> bool:
        source = self._source
        if source is None:
            return False
        try:
            return bool(source())
        except Exception:  # noqa: BLE001 - a closed engine is not playing
            return False

    def note_input(self, *, scrub: bool = False) -> None:
        """The user did something. A scrub, or anything while playing, holds
        background work for ``hold_s``; any input makes pools go to one worker."""
        now = self._clock()
        self._last_input = now
        if scrub or self._playing_now():
            self._hold_until = max(self._hold_until, now + self.hold_s)

    def is_playing(self) -> bool:
        """Playing now, or within the hold after it (or a scrub, or input)."""
        now = self._clock()
        if self._playing_now():
            self._hold_until = max(self._hold_until, now + self.hold_s)
            return True
        return now < self._hold_until

    def interactive(self) -> bool:
        """Playing, or the user gave input in the last ``interactive_s``."""
        return self.is_playing() or self._clock() - self._last_input < self.interactive_s

    def sleep(self, seconds: float, cancel: threading.Event | None = None) -> None:
        if self._sleep is not None:
            self._sleep(seconds)
        elif cancel is not None:
            cancel.wait(seconds)
        else:
            time.sleep(seconds)

    def wait_while_playing(self, cancel: threading.Event | None = None, *,
                           on_pause: Callable[[], None] | None = None,
                           on_resume: Callable[[], None] | None = None) -> bool:
        """Block while ``is_playing()``. False when ``cancel`` was set (at once
        or while waiting); ``on_pause``/``on_resume`` bracket a real wait."""
        paused = False
        try:
            while not (cancel is not None and cancel.is_set()) and self.is_playing():
                if not paused:
                    paused = True
                    if on_pause is not None:
                        on_pause()
                self.sleep(self.poll_s, cancel)
        finally:
            if paused and on_resume is not None:
                on_resume()
        return not (cancel is not None and cancel.is_set())


#: The process-wide gate. ``server.create_app`` makes it watch the engine and
#: feeds it input; tests replace or reset it.
GATE = PlaybackGate()


def gate() -> PlaybackGate:
    return GATE


# -- background threads --------------------------------------------------------

_local = threading.local()


def is_background() -> bool:
    return bool(getattr(_local, "background", False))


def _listener() -> tuple | None:
    return getattr(_local, "listener", None)


def _cancel() -> threading.Event | None:
    return getattr(_local, "cancel", None)


@contextlib.contextmanager
def background(cancel: threading.Event | None = None) -> Iterator[None]:
    """Mark this thread as background work for the block: ``checkpoint`` pauses
    it while audio plays, and pools it starts inherit the mark. ``cancel`` is
    the work's cancel event, which ``checkpoint()`` without one then uses."""
    before = (is_background(), _cancel())
    _local.background = True
    if cancel is not None:
        _local.cancel = cancel
    try:
        yield
    finally:
        _local.background, _local.cancel = before


@contextlib.contextmanager
def listening(on_pause: Callable[[], None] | None,
              on_resume: Callable[[], None] | None) -> Iterator[None]:
    """Tell ``on_pause``/``on_resume`` (a job's "Paused while playing") about every
    wait on this thread and the pool threads it starts."""
    before = _listener()
    _local.listener = (on_pause, on_resume)
    try:
        yield
    finally:
        _local.listener = before


def _inherit() -> tuple:
    return is_background(), _listener(), _cancel()


def _adopt(state: tuple) -> None:
    _local.background, _local.listener, _local.cancel = state
    if state[0]:
        lower_this_thread()


def checkpoint(cancel: threading.Event | None = None, *,
               gate: PlaybackGate | None = None) -> None:
    """Between chunks of heavy work: on a background thread, wait while audio
    plays. Raises ``CancelledError`` when the work's cancel event is set. On a
    foreground thread (a request the UI waits on) it only checks cancel."""
    cancel = cancel if cancel is not None else _cancel()
    if is_background():
        listener = _listener() or (None, None)
        (gate or GATE).wait_while_playing(cancel, on_pause=listener[0],
                                          on_resume=listener[1])
    if cancel is not None and cancel.is_set():
        raise CancelledError


def executor(max_workers: int, name: str = "kuulas-bg") -> ThreadPoolExecutor:
    """A thread pool whose threads inherit the caller's background mark (and its
    pause listener and cancel), at low QoS when background. For pools whose items
    call ``checkpoint`` themselves (export's renderer, imports)."""
    return ThreadPoolExecutor(max_workers=max(1, int(max_workers)),
                              thread_name_prefix=name, initializer=_adopt,
                              initargs=(_inherit(),))


def thread(target: Callable[[], object], name: str) -> threading.Thread:
    """A daemon thread of background work: marked, low QoS, not yet started."""
    def run() -> None:
        _adopt((True, None, None))
        target()
    return threading.Thread(target=run, name=name, daemon=True)


class _Limiter:
    """Admission for one ``gated_map``: no new item while a background caller's
    audio plays; one at a time while interactive."""

    def __init__(self, gate: PlaybackGate, background_: bool,
                 cancel: threading.Event | None):
        self.gate, self.background, self.cancel = gate, background_, cancel
        self.lock = threading.Lock()
        self.active = 0

    def _admit(self) -> bool:
        with self.lock:
            if self.active >= 1 and self.gate.interactive():
                return False
            self.active += 1
            return True

    @contextlib.contextmanager
    def slot(self) -> Iterator[None]:
        listener = _listener() or (None, None)
        while True:
            if self.background:
                self.gate.wait_while_playing(self.cancel, on_pause=listener[0],
                                             on_resume=listener[1])
            if self.cancel is not None and self.cancel.is_set():
                raise CancelledError
            if self._admit():
                break
            self.gate.sleep(self.gate.poll_s, self.cancel)
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1


def gated_map(fn: Callable, items: Iterable, max_workers: int | None = None, *,
              gate: PlaybackGate | None = None,
              cancel: threading.Event | None = None) -> list:
    """``[fn(x) for x in items]`` on up to ``max_workers`` threads, in order,
    under the gate (see ``_Limiter``). The first error is raised; items not yet
    started then never start."""
    items = list(items)
    gate = gate or GATE
    cancel = cancel if cancel is not None else _cancel()
    limiter = _Limiter(gate, is_background(), cancel)
    failed = threading.Event()

    def one(item):
        if failed.is_set():
            raise CancelledError
        try:
            with limiter.slot():
                return fn(item)
        except BaseException:
            failed.set()
            raise

    workers = max(1, min(len(items), max_workers or 1))
    if workers == 1:
        return [one(item) for item in items]
    with executor(workers, "kuulas-analysis") as pool:
        futures = [pool.submit(one, item) for item in items]
        out, errors = [], []
        for future in futures:
            try:
                out.append(future.result())
            except BaseException as e:  # noqa: BLE001 - re-raised below
                errors.append(e)
    if errors:
        # The real failure, not the CancelledError of the items it stopped.
        real = [e for e in errors if not isinstance(e, CancelledError)]
        raise real[0] if real else errors[0]
    return out


# -- operating-system priority -------------------------------------------------

#: macOS ``qos_class_t`` values (``<sys/qos.h>``).
QOS_CLASS_UTILITY = 0x11
QOS_CLASS_BACKGROUND = 0x09
#: ``setpriority(PRIO_DARWIN_PROCESS, 0, PRIO_DARWIN_BG)``: the whole process in
#: the background band (low CPU and throttled disk), ``<sys/resource.h>``.
PRIO_DARWIN_PROCESS = 4
PRIO_DARWIN_BG = 0x1000


def _libc():
    try:
        return ctypes.CDLL(ctypes.util.find_library("c") or None, use_errno=True)
    except OSError:
        return None


def lower_this_thread() -> bool:
    """Ask for utility QoS (macOS) or nice +10 (Linux) on the calling thread.
    Never raises: a refusal costs only the hint. Once per thread."""
    if getattr(_local, "lowered", False):
        return True
    _local.lowered = True
    try:
        if sys.platform == "darwin":
            libc = _libc()
            return libc is not None and libc.pthread_set_qos_class_self_np(
                QOS_CLASS_UTILITY, 0) == 0
        if sys.platform.startswith("linux"):
            tid = threading.get_native_id()
            os.setpriority(os.PRIO_PROCESS, tid,
                           max(os.getpriority(os.PRIO_PROCESS, tid), 10))
            return True
    except (OSError, AttributeError, ValueError):
        pass
    return False


def lower_this_process(*, darwin_background: bool = True, nice: int = 19) -> dict:
    """A process's lowered priority: ``nice`` (never raised back up; IDLE on
    Windows), then with ``darwin_background`` on macOS the Darwin background band
    (efficiency cores, throttled IO) for every thread it has or will start. The
    analysis worker takes nice 10 and no band (``offload.WORKER_NICE``): in the
    band, importing numpy, scipy and speechmix took 4.7 s instead of 0.7 s
    (measured 2026-10-20, load average 12), and on a loaded Mac nice 19 with the
    band never finished at all (owner's ps: ~5% CPU for 11 minutes). What took
    effect, for the selftest."""
    out = {"nice": None, "darwin_background": False}
    with contextlib.suppress(OSError, AttributeError):
        os.nice(max(0, nice - os.getpriority(os.PRIO_PROCESS, 0)))
    with contextlib.suppress(OSError, AttributeError):
        out["nice"] = os.getpriority(os.PRIO_PROCESS, 0)
    if sys.platform == "darwin" and darwin_background:
        libc = _libc()
        if libc is not None:
            with contextlib.suppress(OSError, AttributeError):
                ok = libc.setpriority(PRIO_DARWIN_PROCESS, 0, PRIO_DARWIN_BG) == 0
                libc.pthread_set_qos_class_self_np(QOS_CLASS_BACKGROUND, 0)
                out["darwin_background"] = bool(
                    ok and libc.getpriority(PRIO_DARWIN_PROCESS, 0) == 1)
    if sys.platform == "win32":
        with contextlib.suppress(OSError, AttributeError):
            # IDLE_PRIORITY_CLASS: the Windows counterpart of nice 19.
            kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x40)
    return out
