"""Acceptance guards for internal sync results, without making any edits.

These guards do not authenticate a result supplied by a client. The eventual
session command must retrieve its own stored job result, never trust client
proposal contents, and apply the complete accepted set in one history step.
"""

from __future__ import annotations

import math

from .align_job import snapshot_key
from .model import Project


def validate_acceptance(project: Project, result: dict,
                        accepted: list[str]) -> tuple[str, ...]:
    """Reject stale, unmatched and unexplained proposals before rendering media.

    Only validates the shape and snapshot of a server-owned analysis result.
    No audio variant, clip move, overwrite or history mutation is performed.
    Drift rendering and destination collision checks are separate gates.
    """
    if result.get("snapshot") != snapshot_key(project):
        raise ValueError("stale automatic-sync proposal")
    wanted = set(accepted)
    reference = result.get("reference")
    candidates = result.get("candidates", [])
    by_id = {item.get("clip"): item for item in candidates}
    live = {clip.id for track in project.tracks for clip in track.clips}
    if (not wanted or len(wanted) != len(accepted) or reference in wanted
            or reference not in live or not wanted <= live
            or not wanted <= by_id.keys() or len(by_id) != len(candidates)):
        raise ValueError("invalid automatic-sync acceptance selection")
    for clip_id in accepted:
        item = by_id[clip_id]
        proposal = item.get("proposal")
        delta = item.get("timeline_delta")
        if (item.get("status") != "proposal" or not isinstance(proposal, dict)
                or not isinstance(delta, (float, int)) or not math.isfinite(delta)):
            raise ValueError("invalid automatic-sync proposal")
        values = (proposal.get("offset"), proposal.get("slope"))
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or abs(values[1]) > .002 or len(proposal.get("support", [])) < 3):
            raise ValueError("invalid automatic-sync proposal fit")
        if proposal.get("excluded"):
            raise ValueError("excluded sync windows require boundary validation")
    # Preserve project/measurement ordering, not arbitrary client click order.
    return tuple(item["clip"] for item in candidates if item["clip"] in wanted)
