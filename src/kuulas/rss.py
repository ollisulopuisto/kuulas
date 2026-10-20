"""How much memory this process holds right now (resident set size).

Cheap enough to ask between every chunk of an analysis (docs/MEMORY.md): on
macOS one ``task_info`` call (no ``ps`` process), on Linux ``/proc/self/statm``.
``resource.getrusage`` only gives the *peak*, which never goes down, so it
cannot tell a worker that has just freed a chunk from one that keeps growing.

``setrlimit(RLIMIT_AS)`` is not used for a ceiling: macOS does not enforce it,
and where it is enforced it counts address space, not memory, so numpy and
the BLAS threads' reservations would trip it long before memory runs short.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import subprocess
import sys
from pathlib import Path

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]


class _TimeValue(ctypes.Structure):
    _fields_ = [("seconds", ctypes.c_int), ("microseconds", ctypes.c_int)]


class _MachTaskBasicInfo(ctypes.Structure):
    # <mach/task_info.h>, MACH_TASK_BASIC_INFO (flavor 20); #pragma pack(4).
    _pack_ = 4
    _fields_ = [("virtual_size", ctypes.c_uint64), ("resident_size", ctypes.c_uint64),
                ("resident_size_max", ctypes.c_uint64), ("user_time", _TimeValue),
                ("system_time", _TimeValue), ("policy", ctypes.c_int),
                ("suspend_count", ctypes.c_int)]


_MACH_TASK_BASIC_INFO = 20
_mach = None


def _mach_rss() -> int | None:
    global _mach  # noqa: PLW0603 - the libc handle, looked up once
    if _mach is None:
        try:
            libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.dylib")
            task = ctypes.c_uint.in_dll(libc, "mach_task_self_").value
            fn = libc.task_info
            fn.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p,
                           ctypes.POINTER(ctypes.c_uint)]
            fn.restype = ctypes.c_int
            _mach = (fn, task)
        except (OSError, ValueError, AttributeError):
            _mach = False
    if not _mach:
        return None
    fn, task = _mach
    info = _MachTaskBasicInfo()
    count = ctypes.c_uint(ctypes.sizeof(info) // 4)
    if fn(task, _MACH_TASK_BASIC_INFO, ctypes.byref(info), ctypes.byref(count)) != 0:
        return None
    return int(info.resident_size)


def _ps_rss(pid: int) -> int | None:
    try:
        done = subprocess.run(["/bin/ps", "-o", "rss=", "-p", str(pid)],  # noqa: S603 - fixed arguments
                              capture_output=True, text=True, timeout=3, check=True)
        return int(done.stdout.strip()) * 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def current() -> int | None:
    """Resident bytes of this process now; None where it cannot be read."""
    if sys.platform == "darwin":
        got = _mach_rss()
        if got is not None:
            return got
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        pass
    return _ps_rss(os.getpid())


def peak() -> int | None:
    """The most this process has held resident since it started (bytes)."""
    if resource is None:
        return None
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(raw if sys.platform == "darwin" else raw * 1024)


class Ceiling:
    """A hard memory ceiling checked by the process itself between chunks
    (``priority.checkpoint`` calls ``check`` when it is the memory guard).
    Above ``limit`` bytes it raises ``KuulasError("error.offload.memory")``,
    so the analysis worker fails cleanly with a catalog error, the editor
    shows it and the manager's back-off applies, instead of the Mac swapping.
    ``peak`` is the most seen at a check (what the worker reports)."""

    def __init__(self, limit: int, read=current):
        self.limit = int(limit)
        self._read = read
        self.peak = 0

    def check(self) -> None:
        now = self._read()
        if now is None:
            return
        self.peak = max(self.peak, now)
        if now > self.limit:
            from .messages import KuulasError  # noqa: PLC0415 - messages imports a lot

            raise KuulasError("error.offload.memory", mb=round(now / 1024**2),
                              limit_mb=round(self.limit / 1024**2))


def of(pid: int) -> int | None:
    """Resident bytes of another process (the analysis worker), via ``ps``."""
    if sys.platform.startswith("linux"):
        try:
            pages = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            return None
    return _ps_rss(pid)
