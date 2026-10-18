"""Speaker turns from timed words.

``speaker_turns`` groups consecutive words by the same speaker into turns:
words by one speaker whose gap (``next.s - prev.e``) is at most ``max_gap``
form one turn, and a different speaker always starts a new turn. Errors are
plain ``ValueError``; there is no user-facing text. Inputs are never mutated.
"""

from __future__ import annotations


def speaker_turns(words: list[dict], max_gap: float) -> list[dict]:
    """Group timed words into per-speaker turns.

    ``words`` is a list of dicts with keys ``speaker`` (str), ``s`` and ``e``
    (numbers, ``e >= s``), in time order. Each turn is
    ``{"speaker", "s", "e", "words"}`` where ``words`` is the count and ``e``
    is the greatest word end in the turn. Raises ``ValueError`` when
    ``max_gap`` is negative, a word's end is before its start, or the words
    are not in time order.
    """
    if max_gap < 0:
        msg = f"max_gap must be >= 0, got {max_gap!r}"
        raise ValueError(msg)

    turns: list[dict] = []
    current: dict | None = None
    prev_start: float | None = None
    prev_end: float | None = None

    for word in words:
        speaker = word["speaker"]
        start = word["s"]
        end = word["e"]
        if end < start:
            msg = f"word end must be >= start, got {word!r}"
            raise ValueError(msg)
        if prev_start is not None and start < prev_start:
            msg = f"words must be in time order, got {word!r}"
            raise ValueError(msg)

        if current is None or current["speaker"] != speaker or (
            prev_end is not None and start - prev_end > max_gap
        ):
            current = {"speaker": speaker, "s": start, "e": end, "words": 1}
            turns.append(current)
        else:
            current["e"] = max(current["e"], end)
            current["words"] += 1

        prev_start = start
        prev_end = end

    return turns
