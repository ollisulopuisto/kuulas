"""Which parts of each media file travel when an edit leaves (WP32/WP20).

An edit sent for review or copied into another project does not need the
whole recordings: only the stretches the edit actually uses travel, each
widened by a handle on both sides so the edges keep their context. This
module is the arithmetic of that plan — seconds in, merged ranges out;
reading media, copying files and packaging come later.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

#: One travelling stretch: [start, end) in seconds.
Range = tuple[float, float]
#: The whole plan: per media id, its carried stretches, sorted and merged.
Plan = dict[str, tuple[Range, ...]]


def excerpt_ranges(
    used: Iterable[tuple[str, float, float]],
    *,
    handle: float = 2.0,
    duration: Mapping[str, float] | None = None,
) -> Plan:
    """The parts of each media that travel: every used stretch widened by
    ``handle`` seconds on both sides, clamped to the media's bounds and
    merged.

    ``used`` is ``(media_id, start_seconds, end_seconds)``. A range whose
    end is at or before its start is dropped before the widening — an
    empty or reversed use plays nothing, and a handle is context around
    played audio, not a way to conjure a stretch out of nothing. The
    widened start is never below 0; the widened end is never above
    ``duration[media_id]`` when ``duration`` gives it, and a media it does
    not give is not clamped. A range the clamp empties — a use that starts
    past the media's end — is dropped too, so no empty range can survive
    into the plan. Ranges that overlap or touch merge, because two
    travelling stretches that meet carry the same frames as one. Media
    that keep nothing are absent, and the keys are sorted, so the same
    uses in any order give the same plan.
    """
    widened: dict[str, list[Range]] = {}
    for media_id, start, end in used:
        if end <= start:
            continue
        lo = max(start - handle, 0.0)
        hi = end + handle
        if duration is not None and media_id in duration:
            hi = min(hi, duration[media_id])
        if hi <= lo:
            continue
        widened.setdefault(media_id, []).append((lo, hi))
    plan: Plan = {}
    for media_id in sorted(widened):
        merged: list[Range] = []
        for lo, hi in sorted(widened[media_id]):
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        plan[media_id] = tuple(merged)
    return plan


def total_seconds(plan: Plan) -> float:
    """How many seconds the plan carries, all media together."""
    return float(sum(hi - lo for ranges in plan.values() for lo, hi in ranges))


def savings(plan: Plan, duration: Mapping[str, float]) -> float:
    """The fraction (0 to 1) of the total media duration the plan does NOT
    carry: 0 when the durations sum to 0.

    The total is every duration in ``duration``: a media the plan does not
    carry at all is fully saved. A media the plan carries but the durations
    do not know is outside the accounting — not part of the total. Carried
    seconds are counted per media and never above that media's duration
    (a plan built without durations can overshoot a file's end; carrying a
    whole file twice is still carrying it once), so the fraction stays
    between 0 and 1 for sane input.
    """
    total = sum(duration.values())
    if total == 0:
        return 0.0
    carried = 0.0
    for media_id, ranges in plan.items():
        if media_id not in duration:
            continue
        carried += min(sum(hi - lo for lo, hi in ranges), duration[media_id])
    return (total - carried) / total


def covers(plan: Plan, media_id: str, start: float, end: float) -> bool:
    """Does one range of that media carry the whole stretch
    ``[start, end]``, edges included?

    Two ranges that meet do not: each travelling part must lie inside one
    stretch, or the hand-over would have to stitch files.
    """
    return any(lo <= start and end <= hi for lo, hi in plan.get(media_id, ()))
