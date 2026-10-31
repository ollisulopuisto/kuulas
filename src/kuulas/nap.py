"""Keep the editor out of App Nap while an in-process job runs (macOS).

Exports, masters, automixes and analyses run on the editor's own job pool
(``jobs.py``). When every Kuulas window is hidden, App Nap may throttle the
process — timers coalesce and CPU priority drops — and a forty-minute
master render crawls. Recording and transcription are separate worker
processes (``kuulas_recorder``, ``bgjobs.py``) and are never napped, and
their machine-wide ``caffeinate`` assertions stay as they are; this module
covers only what runs in the editor process itself.

``hold(reason)`` brackets the work with an ``NSProcessInfo`` activity. The
option is ``NSActivityBackground`` on purpose: it only makes the app
ineligible for App Nap. The user-initiated option would also keep the
*display* awake for the whole render, which is the opposite of saving
power; the machine must still sleep on its normal schedule.

Off macOS, without PyObjC, or if the assertion itself fails, ``hold`` is a
no-op: the job still runs, the OS simply keeps its default heuristics.
Like ``desktop.py``, the Cocoa object is injectable so tests need no Mac.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import Iterator
from typing import Any

log = logging.getLogger("kuulas.nap")

#: NSActivityBackground from NSProcessInfo.h: background work of indefinite
#: length; holds off App Nap and nothing else (no display/idle-sleep effect).
NS_ACTIVITY_BACKGROUND = 0x000000FF


@contextlib.contextmanager
def hold(reason: str, *, platform: str | None = None,
         process_info: Any = ...) -> Iterator[None]:
    """Bracket in-process work the OS must not throttle when hidden.

    ``reason`` names the work in Activity Monitor and ``pmset -g
    assertions``. Never raises: a power assertion is never worth a job.
    """
    platform = sys.platform if platform is None else platform
    if platform != "darwin":
        yield
        return
    if process_info is ...:
        try:
            from Foundation import NSProcessInfo  # noqa: PLC0415

            process_info = NSProcessInfo.processInfo()
        except Exception:  # noqa: BLE001 - PyObjC missing or a headless run
            process_info = None
    if process_info is None:
        yield
        return
    token = None
    try:
        token = process_info.beginActivityWithOptions_reason_(
            NS_ACTIVITY_BACKGROUND, reason)
    except Exception as e:  # noqa: BLE001 - see the docstring
        log.debug("could not hold off App Nap for %r: %s", reason, e)
    try:
        yield
    finally:
        if token is not None:
            try:
                process_info.endActivity_(token)
            except Exception as e:  # noqa: BLE001
                log.debug("could not release the App Nap hold for %r: %s",
                          reason, e)
