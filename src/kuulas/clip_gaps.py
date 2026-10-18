"""Gap and overlap report for one track's clips.

``clip_gaps(clips)`` takes ``(start, end)`` whole frames in any order and
returns ``{"gaps": [...], "overlaps": [...]}`` sorted by time. Touching clips
(``end == next start``) give neither a gap nor an overlap. Errors are plain
``ValueError``; there is no user-facing text.
"""

from __future__ import annotations


def clip_gaps(clips: list[tuple[int, int]]) -> dict[str, list[tuple[int, int]]]:
    """Return the gaps and overlaps between the clips, sorted by time.

    A gap is the empty span from the running maximum end to the next clip's
    start when the start is greater; an overlap is the span from a clip's
    start to the smaller of its end and the running maximum end when the
    start is smaller. The input is not mutated.
    """
    gaps: list[tuple[int, int]] = []
    overlaps: list[tuple[int, int]] = []
    running_end: int | None = None
    for start, end in sorted(clips):
        if end <= start:
            msg = f"clip end {end} is not greater than start {start}"
            raise ValueError(msg)
        if running_end is not None:
            if start < running_end:
                overlaps.append((start, min(end, running_end)))
            elif start > running_end:
                gaps.append((running_end, start))
        running_end = end if running_end is None else max(running_end, end)
    return {"gaps": gaps, "overlaps": overlaps}
