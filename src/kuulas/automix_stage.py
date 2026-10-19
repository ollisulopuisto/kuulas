"""Name the automixer's stage from its log message.

The automixer prints progress lines such as ``PROGRESS 5 loaded the tracks``
and log lines such as ``[automixer]   olli: debleed``. Pure Python, stdlib
only: no imports from kuulas. Errors are plain ValueError; there is no
user-facing text.
"""

from __future__ import annotations

import re

_STEP_WORDS = ("debleed", "cleanup", "measure", "dynamics", "lag", "duck", "write")

_DONE = re.compile(r"\bdone\b")

_FLOORS = {
    "load": 0.0,
    "levels": 0.05,
    "speech": 0.15,
    "master": 0.8,
    "write": 0.92,
    "done": 1.0,
}


def stage_of(message: str) -> str | None:
    """Return the automix stage named by ``message``, or None.

    Matching is case-insensitive. Precedence: done, write, master, speech,
    levels, load. A track being processed ("speech") is a line ending in
    `` processed`` or containing one of the step words debleed, cleanup,
    measure, dynamics, lag, duck or write.
    """
    text = message.strip().lower()
    stage: str | None = None
    if _DONE.search(text):
        stage = "done"
    elif "writing the mix" in text:
        stage = "write"
    elif "master" in text or "masterointi" in text:
        stage = "master"
    elif text.endswith(" processed") or any(
            word in text for word in _STEP_WORDS):
        stage = "speech"
    elif "levels" in text:
        stage = "levels"
    elif "load" in text:
        stage = "load"
    return stage


def stage_progress_floor(stage: str) -> float:
    """Return the lowest bar fraction for ``stage``.

    Raises ValueError for an unknown stage.
    """
    try:
        return _FLOORS[stage]
    except KeyError:
        msg = f"unknown automix stage: {stage!r}"
        raise ValueError(msg) from None


def stage_key(stage: str | None) -> str | None:
    """Return the catalog key ``ui.automix.stage.<stage>`` for a known stage.

    None (or an unknown stage) gives None.
    """
    if stage is None or stage not in _FLOORS:
        return None
    return f"ui.automix.stage.{stage}"
