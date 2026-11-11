"""Small cross-platform process queries used by project and worker locks."""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path


def pid_alive(pid: object) -> bool | None:
    """Return whether a PID is alive, or ``None`` when the OS cannot tell.

    ``os.kill(pid, 0)`` is the Unix liveness probe. On Windows it terminates the
    target, so use a query-only process handle there.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if os.name == "nt":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _windows_pid_alive(pid: int) -> bool | None:
    """Query a Windows process without sending it a termination signal."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    open_process.restype = wintypes.HANDLE
    handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # ERROR_INVALID_PARAMETER: no such process.
            return False
        if error == 5:  # ERROR_ACCESS_DENIED: it exists, but cannot be queried.
            return True
        return None

    try:
        get_exit_code = kernel32.GetExitCodeProcess
        get_exit_code.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        get_exit_code.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        exit_code = wintypes.DWORD()
        if not get_exit_code(handle, ctypes.byref(exit_code)):
            return None
        return exit_code.value == 259  # STILL_ACTIVE
    finally:
        close_handle(handle)


def process_group_options() -> dict[str, int | bool]:
    """Start a child in a group that can be stopped without affecting its parent."""
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200)}
    return {"start_new_session": True}


def signal_process_group(proc: subprocess.Popen, sig: int) -> None:
    """Send a stop signal to a child's process group on each supported OS."""
    if os.name == "nt":
        if sig == signal.SIGINT:
            proc.send_signal(getattr(signal, "CTRL_C_EVENT", signal.SIGINT))
        elif sig == signal.SIGTERM:
            proc.terminate()
        else:
            proc.kill()
        return
    os.killpg(proc.pid, sig)


def kill_process_group(proc: subprocess.Popen) -> None:
    """Force-kill a child process group after its graceful stop window."""
    if os.name == "nt":
        proc.kill()
    else:
        os.killpg(proc.pid, signal.SIGKILL)


_CACHE: dict[str, str | None] = {}  # identity tokens never change at runtime


def _cached(name: str, probe: Callable[[], str | None]) -> str | None:
    if name not in _CACHE:
        _CACHE[name] = probe()
    return _CACHE[name]


def boot_id() -> str | None:
    """A token naming this machine's current boot, or ``None`` when the OS has no
    cheap way to tell.

    A pid says nothing across a reboot: the next boot hands the same numbers to
    unrelated processes, and a stored "running" worker would look alive forever.
    A recorded worker pid is therefore trusted only while the boot token matches.
    ``None`` keeps the pid check as the only signal (Windows has no stdlib boot
    timestamp, so the behaviour there is unchanged).

    Linux reads the per-boot UUID (``/proc/sys/kernel/random/boot_id``), not
    ``/proc/stat``'s ``btime``: that is a wall clock and moves with clock sync,
    which would call a live worker interrupted.
    """
    return _cached("boot", _probe_boot_id)


def _probe_boot_id() -> str | None:
    token: str | None = None
    if sys.platform == "darwin":
        sysctl = shutil.which("sysctl")
        if sysctl is not None:
            try:
                out = subprocess.check_output(  # noqa: S603 - resolved, fixed argv
                    [sysctl, "-n", "kern.boottime"], text=True, timeout=5)
            except (OSError, subprocess.SubprocessError):
                out = ""
            match = re.search(r"sec\s*=\s*(\d+)", out)
            token = f"mac-{match.group(1)}" if match else None
    elif os.name == "posix":
        try:
            token = "linux-" + Path("/proc/sys/kernel/random/boot_id").read_text(
                encoding="ascii").strip()
        except OSError:
            token = None
    return token


def machine_id() -> str | None:
    """A stable per-machine token (a hash of the OS machine identity), or ``None``.

    Hostnames lie in both directions: macOS spells one Mac ``name`` and
    ``name.local``, and two Macs can collide under those spellings. The token is
    hashed so project files never carry the raw hardware UUID; only equality is
    ever checked. ``None`` (Windows) keeps the hostname comparison as the only
    signal.
    """
    return _cached("machine", _probe_machine_id)


def _probe_machine_id() -> str | None:
    raw: str | None = None
    if sys.platform == "darwin":
        ioreg = shutil.which("ioreg")
        if ioreg is not None:
            try:
                out = subprocess.check_output(  # noqa: S603 - resolved, fixed argv
                    [ioreg, "-rd1", "-c", "IOPlatformExpertDevice"],
                    text=True, timeout=5)
            except (OSError, subprocess.SubprocessError):
                out = ""
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            raw = match.group(1) if match else None
    elif os.name == "posix":
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                raw = Path(candidate).read_text(encoding="ascii").strip()
            except OSError:
                continue
            if raw:
                break
    return hashlib.sha256(raw.encode()).hexdigest()[:16] if raw else None
