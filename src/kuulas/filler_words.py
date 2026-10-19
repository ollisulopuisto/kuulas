"""Filler word detection in a transcript.

``find_fillers`` reports every word whose text, lower-cased and with leading
and trailing non-alphanumeric characters removed (per ``str.isalnum``), equals
one of the fillers. A word made of a single letter repeated also matches a
filler of length 2 or 3 made of that same letter, when the word is at least as
long as the filler (``"ööööö"`` matches ``"öö"``, ``"mmmm"`` matches ``"mm"``).
``merge_runs`` joins consecutive filler matches (consecutive indexes, gap of
at most ``max_gap`` frames) into runs. Errors are plain ``ValueError``; there
is no user-facing text. Inputs are never mutated.
"""

from __future__ import annotations

DEFAULT_FILLERS: tuple[str, ...] = (
    "öö", "ööö", "öh", "mm", "mmm", "hmm", "um", "uh", "er", "erm",
    "niinku", "tota",
)


def _clean(text: str) -> str:
    """Return ``text`` lower-cased with leading/trailing non-alnum removed."""
    start = 0
    length = len(text)
    while start < length and not text[start].isalnum():
        start += 1
    end = length
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return text[start:end].lower()


def _single_letter_repeat(text: str) -> bool:
    return bool(text) and all(ch == text[0] for ch in text)


def _matches(cleaned: str, filler: str) -> bool:
    if cleaned == filler:
        return True
    if 2 <= len(filler) <= 3 and _single_letter_repeat(filler):
        return (_single_letter_repeat(cleaned)
                and cleaned[0] == filler[0]
                and len(cleaned) >= len(filler))
    return False


def find_fillers(words, fillers=DEFAULT_FILLERS):
    """Return filler matches for ``words``.

    Each match is ``{"index", "text", "start", "end}`` using the word's own
    text and frame positions. A word missing ``text``, ``start`` or ``end``
    raises ``ValueError``. An empty ``fillers`` finds nothing.
    """
    fillers = [filler.lower() for filler in fillers]
    found = []
    for index, word in enumerate(words):
        try:
            text = word["text"]
            start = word["start"]
            end = word["end"]
        except KeyError as exc:
            msg = f"word is missing key {exc.args[0]!r}"
            raise ValueError(msg) from exc
        cleaned = _clean(text)
        if not cleaned:
            continue
        if any(_matches(cleaned, filler) for filler in fillers):
            found.append({"index": index, "text": text, "start": start,
                          "end": end})
    return found


def merge_runs(found, max_gap):
    """Join consecutive filler matches into runs.

    Consecutive means indexes follow one another (index + 1) and the gap from
    one match's ``end`` to the next match's ``start`` is at most ``max_gap``
    frames. Each run is ``{"start", "end", "indexes"}``. ``max_gap`` below 0
    raises ``ValueError``.
    """
    if max_gap < 0:
        msg = f"max_gap must not be negative, got {max_gap!r}"
        raise ValueError(msg)
    runs = []
    current = None
    last_end = 0
    for item in found:
        index = item["index"]
        start = item["start"]
        end = item["end"]
        if current is None:
            current = {"start": start, "end": end, "indexes": [index]}
            last_end = end
            continue
        if (index == current["indexes"][-1] + 1
                and start - last_end <= max_gap):
            current["end"] = end
            current["indexes"].append(index)
            last_end = end
        else:
            runs.append(current)
            current = {"start": start, "end": end, "indexes": [index]}
            last_end = end
    if current is not None:
        runs.append(current)
    return runs
