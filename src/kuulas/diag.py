"""Playback diagnostics, on with ``--debug`` (developer output, English only).

Why it exists: on a laptop the engine said "playback cannot keep up" and
nobody knew whether the disk (a synced folder), the mixing or something else
was slow. With the switch on, the audio callback times itself and the media
reads with ``time.perf_counter`` into fixed-size ring buffers made up front;
a reporter thread (never the audio thread) reads them once a second.

**The audio thread's part is a few list assignments**: no allocation worth
the name, no I/O, no lock. Each ring has exactly one writing thread (the
callback, or the prefetch helper), so no lock is needed; a reader may see an
entry half a step old, which for a once-a-second report does not matter.

Off (the default), none of this exists: the engine holds no ``Probe``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

#: Callbacks kept (about 11 s at 1024 frames and 48 kHz) and reads kept per
#: thread. Enough for a one-second report to find all of its entries.
CALLBACK_RING = 512
READ_RING = 256
#: Reads named in a report line.
SLOWEST = 3

_enabled = False
#: Where a reader is in (callbacks, mixer reads, prefetch reads, misses).
Cursor = tuple[int, int, int, int]


def enable() -> None:
    """Turn diagnostics on for engines made from now on (``--debug``)."""
    global _enabled  # noqa: PLW0603 - one process-wide switch, set once by the CLI
    _enabled = True


def disable() -> None:
    global _enabled  # noqa: PLW0603
    _enabled = False


def enabled() -> bool:
    return _enabled


def emit(line: str) -> None:
    """One diagnostic line to stderr."""
    print(line, file=sys.stderr, flush=True)


class Ring:
    """A fixed-size ring of ``(a, b, c)`` entries; ``push`` replaces the oldest.
    ``count`` is how many were ever pushed, which is a reader's cursor."""

    def __init__(self, size: int):
        self.size = size
        self.count = 0
        self._a: list[Any] = [0.0] * size
        self._b: list[Any] = [0.0] * size
        self._c: list[Any] = [0.0] * size

    def push(self, a: Any, b: Any, c: Any) -> None:
        i = self.count % self.size
        self._a[i], self._b[i], self._c[i] = a, b, c
        self.count += 1

    def since(self, cursor: int) -> list[tuple[Any, Any, Any]]:
        """Entries pushed after ``cursor`` (all that are left, if it fell
        behind the ring), oldest first. Reader side: allocates."""
        end = self.count
        start = max(cursor, end - self.size)
        return [(self._a[k % self.size], self._b[k % self.size], self._c[k % self.size])
                for k in range(start, end)]


def slow_component(total: float, reads: float, mix: float) -> str:
    """Which part of a callback that took ``total`` was the largest: the media
    reads, the mixing, or everything else (copying, resampling, locks)."""
    other = total - reads - mix
    if reads >= mix and reads >= other:
        return "reads"
    return "mix" if mix >= other else "other"


class Probe:
    """The rings and the audio thread's read accumulator."""

    def __init__(self) -> None:
        #: per callback: (total s, reads s, mix s)
        self.callbacks = Ring(CALLBACK_RING)
        #: per callback, pushed together with ``callbacks``: (wait s, 0, 0).
        #: ``wait`` is wall time minus the thread's CPU time: the time the
        #: callback was not running (the GIL held by another thread, a
        #: preempted core, or I/O).
        self.waits = Ring(CALLBACK_RING)
        #: per read-ahead miss (the callback found nothing cached and played
        #: silence for that source): (0, 0, media id)
        self.misses = Ring(READ_RING)
        #: per media read: (seconds, 0, media id); one ring per writing thread
        self.mixer_reads = Ring(READ_RING)
        self.prefetch_reads = Ring(READ_RING)
        #: read time of the callback in progress (audio thread only)
        self.acc = 0.0

    def callback(self, total: float, reads: float, mix: float,
                 wait: float = 0.0) -> None:
        self.callbacks.push(total, reads, mix)
        self.waits.push(wait, 0.0, 0.0)

    def miss(self, media_id: str) -> None:
        self.misses.push(0.0, 0.0, media_id)

    def mixer_read(self, seconds: float, media_id: str) -> None:
        self.acc += seconds
        self.mixer_reads.push(seconds, 0.0, media_id)

    def prefetch_read(self, seconds: float, media_id: str) -> None:
        self.prefetch_reads.push(seconds, 0.0, media_id)

    def cursor(self) -> Cursor:
        return (self.callbacks.count, self.mixer_reads.count, self.prefetch_reads.count,
                self.misses.count)

    def summary(self, since: Cursor, block_ms: float,
                name_of: Callable[[str], str]) -> tuple[dict[str, Any], Cursor]:
        """Numbers for everything recorded after the ``since`` cursor, and the
        cursor to pass next time. Times in milliseconds. ``slow`` is None
        unless the worst callback took longer than the block lasts."""
        cursor = self.cursor()
        calls = self.callbacks.since(since[0])
        mixer = self.mixer_reads.since(since[1])
        prefetch = self.prefetch_reads.since(since[2])
        misses = self.misses.since(since[3])
        # Same cursor as the callbacks; a reader may see a callback whose wait
        # is not pushed yet, so line the two up from the end.
        waits = [w[0] for w in self.waits.since(since[0])][:len(calls)]
        waits += [0.0] * (len(calls) - len(waits))
        n = len(calls)
        worst = max(calls, default=(0.0, 0.0, 0.0))
        worst_wait = waits[calls.index(worst)] if calls else 0.0
        slowest = sorted(mixer + prefetch, key=lambda r: r[0], reverse=True)[:SLOWEST]
        out = {
            "block_ms": block_ms,
            "callbacks": n,
            "cb_avg_ms": sum(c[0] for c in calls) / n * 1000 if n else 0.0,
            "cb_max_ms": worst[0] * 1000,
            "reads_avg_ms": sum(c[1] for c in calls) / n * 1000 if n else 0.0,
            "reads_max_ms": max((c[1] for c in calls), default=0.0) * 1000,
            "mix_avg_ms": sum(c[2] for c in calls) / n * 1000 if n else 0.0,
            "mix_max_ms": max((c[2] for c in calls), default=0.0) * 1000,
            "prefetch_reads": len(prefetch),
            "prefetch_ms": sum(r[0] for r in prefetch) * 1000,
            "prefetch_max_ms": max((r[0] for r in prefetch), default=0.0) * 1000,
            "slowest_reads": [{"name": name_of(r[2]), "ms": r[0] * 1000}
                              for r in slowest],
            "slow": None,
            "miss": len(misses),
            "wait_max_ms": max(waits, default=0.0) * 1000,
        }
        if worst[0] * 1000 > block_ms:
            out["slow"] = slow_component(*worst)
            # Late while the thread mostly was not running and the time was
            # not a read: someone else held the GIL (the web server, a
            # garbage collection) or the core.
            if worst_wait - worst[1] >= 0.5 * worst[0]:
                out["slow"] += " gil?"
        return out, cursor


def format_report(s: dict[str, Any]) -> str:
    """The once-a-second line. ``s`` is a ``Probe.summary`` plus the engine's
    counters and device."""
    line = (f"kuulas debug: block {s['block_ms']:.1f} ms, "
            f"callback avg {s['cb_avg_ms']:.1f} max {s['cb_max_ms']:.1f} ms "
            f"({s['callbacks']} blocks), late {s['late_blocks']} "
            f"failed {s['failed_blocks']} miss {s.get('miss', 0)}, "
            f"{s['device']} {s['device_rate']} Hz")
    if s["resampling"]:
        line += " resampling"
    if s["slow"]:
        line += f", slow: {s['slow']} (waited {s.get('wait_max_ms', 0.0):.1f} ms)"
    reads = ", ".join(f"{r['name']}: {r['ms']:.1f}" for r in s["slowest_reads"])
    return f"{line}, slowest reads (ms) {reads}" if reads else line


def format_raise(old: int, new: int, late: int, cb_max_ms: float,
                 block_ms: float) -> str:
    """The line for a buffer raised after late blocks, with what caused it."""
    return (f"kuulas debug: buffer {old} -> {new} frames after {late} late blocks; "
            f"callback max {cb_max_ms:.1f} ms against a block of {block_ms:.1f} ms")
