"""Words and time ranges.

Select the words whose midpoint falls inside any of several time ranges, and
build merged time ranges from a list of words. Pure Python, stdlib only: no
imports from kuulas. Errors are plain ValueError; there is no user-facing
text.
"""

from __future__ import annotations


def words_in_ranges(
    words: list[dict], ranges: list[tuple[float, float]]
) -> list[dict]:
    """Return the words whose midpoint lies in any of ``ranges``.

    Each range is ``(start, end)`` with ``start`` inclusive and ``end``
    exclusive: a word matches when ``start <= (s + e) / 2 < end``. Matches are
    returned as shallow copies in input order. Raises ``ValueError`` for a
    range with ``end <= start``.
    """
    for start, end in ranges:
        if end <= start:
            msg = f"range ({start}, {end}) has end <= start"
            raise ValueError(msg)
    kept: list[dict] = []
    for word in words:
        midpoint = (word["s"] + word["e"]) / 2
        if any(start <= midpoint < end for start, end in ranges):
            kept.append(dict(word))
    return kept


def ranges_of_words(
    words: list[dict], pad: float = 0.0, join_gap: float = 0.0
) -> list[tuple[float, float]]:
    """Return one ``(s - pad, e + pad)`` range per word, merged by ``join_gap``.

    Words are sorted by ``s`` first. Each range's start is clamped at 0.
    Neighbouring ranges are merged when the gap between them is at most
    ``join_gap``. Raises ``ValueError`` for negative ``pad`` or ``join_gap``.
    The input is not mutated.
    """
    if pad < 0:
        msg = f"pad must be >= 0, got {pad}"
        raise ValueError(msg)
    if join_gap < 0:
        msg = f"join_gap must be >= 0, got {join_gap}"
        raise ValueError(msg)

    spans: list[tuple[float, float]] = []
    for word in sorted(words, key=lambda w: w["s"]):
        start = max(0.0, word["s"] - pad)
        end = word["e"] + pad
        spans.append((start, end))

    merged: list[tuple[float, float]] = []
    for start, end in spans:
        if merged and start - merged[-1][1] <= join_gap:
            _, prev_end = merged[-1]
            merged[-1] = (merged[-1][0], max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
