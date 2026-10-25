"""The Material list: every recording of the project and how much of it the edit plays
(docs/design/MATERIAL.md, BUGS #82). Pure: a Project in, plain rows out. Nothing here
changes a recording or the project."""

from __future__ import annotations

from collections.abc import Collection

from . import source_map
from .clock import FLICKS
from .model import Project

#: A recording with no more than this many seconds not played counts as played whole
#: (rounding at the very ends).
_WHOLE_S = 0.05


def _seconds(ranges: list[tuple[int, int]]) -> float:
    return round(sum(end - start for start, end in ranges) / FLICKS, 3)


def rows(project: Project, *, missing: Collection[str] = (),
         recorded: Collection[str] = ()) -> list[dict]:
    """One row per recording (excerpts belong to their original and are left out), newest
    first (the project lists media in the order they came in). ``used_s`` is what the edit
    plays, ``cut_s`` what only muted or silenced clips cover, ``unused_s`` the rest;
    ``state`` is "used" (all of it), "partly", "cut" (only muted) or "unused" (not on the
    timeline). ``missing``: media ids whose file is gone; ``recorded``: ids that were
    recorded in the project (a take)."""
    out = []
    for media in reversed(project.media):
        if media.excerpt_of:
            continue
        used, cut, unused = source_map.coverage(project, media.sha256)
        used_s, cut_s, unused_s = _seconds(used), _seconds(cut), _seconds(unused)
        if used_s == 0.0 and cut_s == 0.0:
            state = "unused"
        elif used_s == 0.0:
            state = "cut"
        elif cut_s + unused_s <= _WHOLE_S:
            state = "used"
        else:
            state = "partly"
        out.append({
            "id": media.id, "name": media.name, "sha256": media.sha256,
            "seconds": round(media.frames / project.rate, 3), "channels": media.channels,
            "used_s": used_s, "cut_s": cut_s, "unused_s": unused_s, "state": state,
            "missing": media.id in missing, "recorded": media.id in recorded})
    return out
