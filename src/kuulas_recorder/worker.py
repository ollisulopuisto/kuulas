"""The worker process: opens the input, runs the capture, reports to the supervisor.

Started by the supervisor as ``python -m kuulas_recorder worker``. The first
line on stdin is the JSON config; later lines are commands (``stop``). Every
event goes to stdout as one JSON line. The worker never waits on the
supervisor: events are handed to a reporter thread, and level reports are
dropped (not queued) if the supervisor stops reading. When stdin closes (the
supervisor is gone) the worker stops cleanly, so it never records on with
nobody to stop it.

Exit codes tell the supervisor what to do next (docs/RECORDER.md).
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
import sys
import threading
from typing import BinaryIO, TextIO

from kuulas_recorder.capture import Capture
from kuulas_recorder.sources import SourceError, make_source

EXIT_OK = 0
EXIT_DEVICE_LOST = 2
EXIT_DISK_FULL = 3
EXIT_OPEN_FAILED = 4
EXIT_WRITE_FAILED = 5
EXIT_BAD_CONFIG = 6

# Level reports beyond this many queued events are dropped: they are only
# meters, and a backlog means the supervisor is not reading.
_LEVEL_BACKLOG = 50


class Reporter:
    """Writes events to the supervisor from its own thread; ``put`` never blocks."""

    def __init__(self, out: BinaryIO, on_gone):
        self._out = out
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._on_gone = on_gone
        self.dropped_levels = 0
        self.gone = False
        self._thread = threading.Thread(target=self._run, name="reporter", daemon=True)
        self._thread.start()

    def put(self, ev: dict) -> None:
        if ev.get("ev") == "levels" and self._q.qsize() > _LEVEL_BACKLOG:
            self.dropped_levels += 1
            return
        self._q.put(ev)

    def _run(self) -> None:
        while True:
            ev = self._q.get()
            if ev is None:
                return
            if self.gone:
                continue
            try:
                self._out.write(json.dumps(ev).encode() + b"\n")
                self._out.flush()
            except (OSError, ValueError):
                self.gone = True
                self._on_gone()

    def close(self, timeout: float = 3.0) -> None:
        self._q.put(None)
        self._thread.join(timeout)


def _read_commands(stdin: TextIO, stop: threading.Event, why: list[str],
                   cap: Capture) -> None:
    for line in stdin:
        text = line.strip()
        if text == "stop":
            why.append("stopped")
            stop.set()
        elif text.startswith("{"):
            # {"cmd": "record", folder, take, names}: an armed worker starts the take
            # (the pre-roll first). Anything else is ignored.
            try:
                msg = json.loads(text)
                if msg.get("cmd") == "record":
                    cap.begin(msg["folder"], msg["take"], list(msg["names"]))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    # stdin closed: the supervisor is gone. Stop cleanly rather than record on
    # with nobody able to stop it.
    why.append("supervisor_gone")
    stop.set()


def run(config: dict, stdin: TextIO, out: BinaryIO) -> int:
    stop = threading.Event()
    why: list[str] = []
    reporter = Reporter(out, on_gone=stop.set)
    try:
        return _run(config, stdin, reporter, stop, why)
    finally:
        reporter.close()


def _run(config: dict, stdin: TextIO, reporter: Reporter, stop: threading.Event,
         why: list[str]) -> int:
    report = reporter.put
    report({"ev": "hello", "pid": os.getpid()})
    try:
        channels = [int(c) for c in config["channels"]]
        source = make_source(config.get("device"), max(channels), int(config["rate"]),
                             int(config.get("blocksize", 1024)))
        kwargs = {k: config[k] for k in ("flush_seconds", "ring_seconds",
                                         "max_data_bytes", "blocksize") if k in config}
        armed = bool(config.get("armed"))
        # Armed (pre-roll): no take yet; the folder, take and names come with "record".
        cap = Capture(source, folder=config.get("folder"), take=config.get("take"),
                      channels=channels, names=list(config.get("names") or []),
                      rate=int(config["rate"]), segment=int(config.get("segment", 1)),
                      report=report, armed=armed,
                      preroll_seconds=float(config.get("preroll_seconds", 0)), **kwargs)
    except (KeyError, TypeError, ValueError) as e:
        report({"ev": "error", "key": "bad_config", "text": f"Bad worker config: {e}"})
        return EXIT_BAD_CONFIG
    try:
        cap.start()
    except SourceError as e:
        report({"ev": "error", "key": e.key, "text": e.text})
        return EXIT_OPEN_FAILED
    except FileExistsError as e:
        report({"ev": "error", "key": "file_exists",
                "text": f"{e.filename} already exists; a take is never overwritten."})
        return EXIT_OPEN_FAILED
    except OSError as e:
        report({"ev": "error", "key": "folder_not_writable",
                "text": f"Cannot write the take: {e.strerror or e}"})
        return EXIT_OPEN_FAILED
    report({"ev": "started", "device": source.describe()})
    threading.Thread(target=_read_commands, args=(stdin, stop, why, cap), name="stdin",
                     daemon=True).start()
    with contextlib.suppress(ValueError):  # not the main thread (in-process tests)
        signal.signal(signal.SIGTERM, lambda *_: (why.append("terminated"), stop.set()))
    code = EXIT_OK
    while not stop.wait(0.05):
        state = cap.poll()
        if state == "device_lost":
            report({"ev": "device_lost", "reason": cap.lost_reason})
            code = EXIT_DEVICE_LOST
            break
        if state == "error":
            break
    cap.stop()
    if cap.error is not None:
        return EXIT_DISK_FULL if cap.error[0] == "disk_full" else EXIT_WRITE_FAILED
    if code == EXIT_OK:
        report({"ev": "stopped", "reason": why[0] if why else "stopped",
                "dropped_level_reports": reporter.dropped_levels})
    return code


def main() -> int:
    # Ctrl+C in a terminal signals the whole process group; only the supervisor
    # decides when a take stops.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    # The audio callback must take the GIL before it runs. With a thread that
    # never sleeps holding it, the callback waited up to 22 ms at Python's
    # default 5 ms switch interval and 4 ms at 1 ms (tests/manual/
    # test_recorder_bench.py, 2026-10-19). The worker has no such thread; this
    # caps the cost if one ever appears (a library, a stuck reporter).
    sys.setswitchinterval(0.001)
    line = sys.stdin.readline()
    try:
        config = json.loads(line)
    except ValueError:
        sys.stderr.write("kuulas-recorder worker: the first stdin line must be JSON\n")
        return EXIT_BAD_CONFIG
    return run(config, sys.stdin, sys.stdout.buffer)
