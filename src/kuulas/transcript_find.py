"""Find words in a transcript timeline.

Pure text-search helpers over the word dicts returned by
:func:`kuulas.transcript.timeline_words`.
"""

from __future__ import annotations

import unicodedata


def normalise(text: str) -> str:
    """Lower-case *text*, drop accents, and remove punctuation.

    Digits are kept and whitespace is kept so multi-word queries survive.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    cleaned = "".join(
        c
        for c in decomposed
        if not unicodedata.combining(c)
        and (c.isalpha() or c.isdigit() or c.isspace())
    )
    return cleaned.casefold()


def find(words: list[dict], query: str) -> tuple[tuple[int, ...], ...]:
    """Return every match of *query* against *words*.

    Each match is a tuple of consecutive indices into *words*, which is the
    list returned by :func:`kuulas.transcript.timeline_words` and is therefore
    in timeline order.

    A single-word query matches when it is a prefix of a normalised word, but
    only when the query is at least two characters. A multi-word query matches
    a run of consecutive words: each query word must be a prefix of the
    corresponding timeline word. Matches never cross track boundaries.

    An empty query, or one that contains only punctuation, returns an empty
    tuple.
    """
    query_parts = normalise(query).split()
    if not query_parts:
        return ()
    if len(query_parts) == 1 and len(query_parts[0]) < 2:
        return ()

    normalised = [normalise(w["w"]) for w in words]
    width = len(query_parts)
    last_start = len(words) - width
    matches: list[tuple[int, ...]] = []

    for start in range(last_start + 1):
        if not _match_from(words, normalised, start, query_parts):
            continue
        matches.append(tuple(range(start, start + width)))

    return tuple(matches)


def _match_from(
    words: list[dict],
    normalised: list[str],
    start: int,
    query_parts: list[str],
) -> bool:
    """Check whether *query_parts* matches *words* starting at *start*."""
    track = words[start]["track"]
    for offset, part in enumerate(query_parts):
        word = normalised[start + offset]
        if words[start + offset]["track"] != track:
            return False
        if not word.startswith(part):
            return False
    return True


def next_match(
    matches: tuple[tuple[int, ...], ...],
    position: int,
) -> tuple[int, ...] | None:
    """The first match that starts after *position*, wrapping around."""
    if not matches:
        return None
    for match in matches:
        if match[0] > position:
            return match
    return matches[0]


def prev_match(
    matches: tuple[tuple[int, ...], ...],
    position: int,
) -> tuple[int, ...] | None:
    """The last match that starts before *position*, wrapping around."""
    if not matches:
        return None
    for match in reversed(matches):
        if match[0] < position:
            return match
    return matches[-1]
