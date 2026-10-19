"""The three sync states of a clip (R51, WP19a): never guessed, never auto-fixed.

- ``in_sync``: the clip sits where its sync group puts it (or has no group).
- ``free``: the user declared the offset deliberate (``Clip.free``).
- ``drift``: it sits somewhere else and nobody said that is on purpose.

Pure: the project in, the state out. The reference is ``ops.synced_start``, the
same rule as ``ops.resync``, so what the badge shows is what resync would undo.
The *cause* of a drift (which edit moved it) is
history, not model: ``cause`` finds the step, ``Session.sync_cause`` describes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import ops
from .model import Clip, Project

IN_SYNC = "in_sync"
FREE = "free"
DRIFT = "drift"


@dataclass(frozen=True)
class SyncState:
    state: str
    #: Frames the clip sits after (positive) or before (negative) where its group
    #: puts it; 0 for a clip with no reference.
    offset: int = 0


def sync_state(p: Project, clip: Clip | str) -> SyncState:
    """The state of ``clip`` (a clip or its id) in ``p``."""
    if isinstance(clip, str):
        clip = p.clip(clip)
    want = ops.synced_start(p, clip)
    offset = 0 if want is None else clip.start - want
    if clip.free:
        return SyncState(FREE, offset)
    return SyncState(DRIFT if offset else IN_SYNC, offset)


@dataclass(frozen=True)
class Drift:
    clip_id: str
    track_id: str
    start: int
    offset: int
    state: str = DRIFT


def overview(p: Project) -> list[Drift]:
    """Every clip the timeline marks: those in undecided drift (red badge) and
    those declared free (grey icon, with their offset), in timeline order."""
    found = []
    for track in p.tracks:
        for clip in track.clips:
            s = sync_state(p, clip)
            if s.state != IN_SYNC:
                found.append(Drift(clip.id, track.id, clip.start, s.offset, s.state))
    return sorted(found, key=lambda d: (d.start, d.clip_id))


def drifts(p: Project) -> list[Drift]:
    """Every clip in undecided drift, in timeline order (the list ] and [ step
    through). Free clips are never on it."""
    return [d for d in overview(p) if d.state == DRIFT]


def cause(states: list[Project], clip_id: str) -> int | None:
    """Index into ``states`` (oldest first, the last is the current one) of the
    first state from which ``clip_id`` has drifted by its current offset without
    a break, or None when it is not drifting now. The caller maps the index to
    the history step that produced that state."""
    last = states[-1]
    if not _has(last, clip_id):
        return None
    now = sync_state(last, clip_id)
    if now.state != DRIFT:
        return None
    first = len(states) - 1
    for i in range(len(states) - 2, -1, -1):
        if not _has(states[i], clip_id):
            break
        s = sync_state(states[i], clip_id)
        if s.state != DRIFT or s.offset != now.offset:
            break
        first = i
    return first


def _has(p: Project, clip_id: str) -> bool:
    try:
        p.clip(clip_id)
    except KeyError:
        return False
    return True
