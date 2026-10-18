"""Speaking statistics from a timeline transcript.

Pure logic over the word dicts ``transcript.timeline_words`` returns.
"""

from __future__ import annotations

from itertools import pairwise

#: A new turn is counted when the gap between consecutive unmuted words
#: exceeds this many seconds.
TURN_GAP_SECONDS = 1.5


def speaker_stats(
    words: list[dict], *, rate: int = 48_000
) -> dict[str, dict[str, float | int]]:
    """Return per-speaker statistics for the unmuted words on the timeline.

    The speaker key is the mapped person id when one is present, otherwise
    the raw ``spk`` label, otherwise the track id.  Muted words are left out.

    Each value is ``{"words": n, "seconds": s, "turns": n, "wpm": n}``.
    ``seconds`` is the total speaking time of the kept words, ``turns``
    increases on a speaker change or on a gap over ``TURN_GAP_SECONDS``
    between consecutive kept words, and ``wpm`` is words per minute of
    speaking time rounded to one decimal place (0 when there is no time).
    """
    heard = sorted(
        (w for w in words if not w.get("muted")), key=lambda w: (w["s"], w["track"])
    )
    raw: dict[str, dict[str, float | int]] = {}
    prev: dict | None = None

    for w in heard:
        speaker = _speaker(w)
        stats = raw.setdefault(speaker, {"words": 0, "seconds": 0.0, "turns": 0})
        stats["words"] = int(stats["words"]) + 1
        duration = (w["e"] - w["s"]) / rate
        stats["seconds"] = float(stats["seconds"]) + duration

        new_turn = prev is None or _speaker(prev) != speaker
        if prev is not None and not new_turn:
            gap = (w["s"] - prev["e"]) / rate
            new_turn = gap > TURN_GAP_SECONDS
        if new_turn:
            stats["turns"] = int(stats["turns"]) + 1
        prev = w

    for stats in raw.values():
        seconds = float(stats["seconds"])
        stats["wpm"] = round(int(stats["words"]) * 60 / seconds, 1) if seconds > 0 else 0

    return raw


def shares(stats: dict[str, dict[str, float | int]]) -> dict[str, float]:
    """Return each speaker's share of total speaking time as a float 0 to 1.

    Shares sum to 1.  An empty input returns an empty dict.
    """
    total = sum(float(v.get("seconds", 0)) for v in stats.values())
    if total == 0:
        return {}
    return {k: float(v.get("seconds", 0)) / total for k, v in stats.items()}


def longest_silences(
    words: list[dict], n: int = 5, *, rate: int = 48_000
) -> list[tuple[float, float]]:
    """Return the ``n`` longest gaps between consecutive unmuted words.

    Each gap is returned as ``(start_seconds, end_seconds)``, longest first.
    """
    heard = sorted(
        (w for w in words if not w.get("muted")), key=lambda w: (w["s"], w["track"])
    )
    gaps: list[tuple[float, float, float]] = []
    for prev, cur in pairwise(heard):
        gap = (cur["s"] - prev["e"]) / rate
        if gap > 0:
            gaps.append((gap, prev["e"] / rate, cur["s"] / rate))
    gaps.sort(reverse=True)
    return [(start, end) for _gap, start, end in gaps[: max(0, n)]]


def _speaker(w: dict) -> str:
    """Speaker key: mapped person, raw spk label, or track id."""
    return w.get("person") or w.get("spk") or w.get("track") or ""
