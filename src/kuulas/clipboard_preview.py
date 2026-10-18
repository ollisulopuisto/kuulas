"""The play-preview of a clipboard entry (WP46): the plan, not the playing.

``preview_project`` builds a throw-away project holding only the entry's clips,
from frame 0, on the current project's tracks, so the engine can play it
exactly as a paste would sound (same clips, same gain/pan/fades/envelopes)
without the real project changing, committing to history or being saved. Pure:
no audio, no session, no files.
"""

from __future__ import annotations

from dataclasses import replace

from .clipboard import Entry
from .model import Project
from .paste_apply import apply_paste
from .paste_plan import plan_paste


def preview_project(project: Project,
                    entry: Entry) -> tuple[Project | None, tuple[str, ...]]:
    """``(temporary project, missing media digests)``; the project is None when
    nothing of the entry can be heard (no tracks, or none of its media here).

    Track level controls (mute, solo, bus, automation, gate) are cleared so the
    preview is always audible and is the entry itself; track gain and pan stay.
    An entry with more source tracks than the project has folds its extra
    slots onto the last track.
    """
    if not project.tracks:
        return None, ()
    bare = replace(
        project,
        tracks=tuple(replace(t, clips=(), mute=False, solo=False, bus=None,
                             automation=(), gate=()) for t in project.tracks),
        buses=(), markers=(), placeholders=(), sync_groups=(),
    )
    last = len(bare.tracks) - 1
    slots = {ref.track_slot for ref in entry.refs}
    mapping = {slot: bare.tracks[min(slot, last)].id for slot in slots}
    plan = plan_paste(bare, entry, 0, "overwrite", mapping)
    if not plan.placements:
        return None, plan.missing
    return apply_paste(bare, entry, plan, 0, set(), "overwrite"), plan.missing
