"""Talk time per speaker.

``talk_share`` totals each speaker's active frames (their ranges merged first),
the length of the union of all speakers' ranges, and the length where two or
more speakers are active at once. Shares are per-speaker frames divided by the
per-speaker sum (0.0 for everyone when that sum is 0). Errors are plain
``ValueError``; there is no user-facing text. Inputs are never mutated.
"""

from __future__ import annotations


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Validate ranges and merge overlapping or touching ones."""
    normalized: list[tuple[int, int]] = []
    for r in ranges:
        try:
            start, end = r  # type: ignore[misc]
        except (TypeError, ValueError):
            msg = f"range {r!r} is not a (start, end) pair"
            raise ValueError(msg) from None
        if end <= start:
            msg = f"range end must be greater than start, got {r!r}"
            raise ValueError(msg)
        normalized.append((start, end))
    normalized.sort()
    merged: list[list[int]] = []
    for start, end in normalized:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def talk_share(
    speakers: dict[str, list[tuple[int, int]]]
) -> dict[str, object]:
    """Return per-speaker frame totals, union length, overlap, and shares.

    ``speakers`` maps a name to a list of ``(start, end)`` frame ranges with
    ``end > start``. A speaker's ranges may overlap and are merged first.
    Raises ``ValueError`` when a range's end is not greater than its start.
    """
    per_speaker: dict[str, int] = {}
    events: list[tuple[int, int]] = []
    for name, ranges in speakers.items():
        merged = _merge(list(ranges))
        per_speaker[name] = sum(end - start for start, end in merged)
        for start, end in merged:
            events.append((start, 1))
            events.append((end, -1))

    total = 0
    overlap = 0
    if events:
        events.sort()
        active = 0
        prev_time = events[0][0]
        index = 0
        count = len(events)
        while index < count:
            time = events[index][0]
            if time > prev_time:
                length = time - prev_time
                if active >= 1:
                    total += length
                if active >= 2:
                    overlap += length
            while index < count and events[index][0] == time:
                active += events[index][1]
                index += 1
            prev_time = time

    per_speaker_sum = sum(per_speaker.values())
    if per_speaker_sum == 0:
        share = dict.fromkeys(per_speaker, 0.0)
    else:
        share = {
            name: per_speaker[name] / per_speaker_sum for name in per_speaker
        }
    return {
        "per_speaker": per_speaker,
        "total": total,
        "overlap": overlap,
        "share": share,
    }
