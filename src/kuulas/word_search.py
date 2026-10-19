"""Search transcript words and determine media coverage (T64).

Matches single words or multi-word phrases against words with time offsets,
and determines if a hit is inside, cut from, or partly in active audio windows.
"""

from __future__ import annotations

import string
from typing import Any

_PUNCT = (
    string.punctuation
    + "\u2013\u2014\u2026\u00ab\u00bb\u201c\u201d\u2018\u2019\u201e"
)
EPS = 1e-9


def _clean(token: str) -> str:
    return token.strip(_PUNCT).casefold()


def find_hits(
    words: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """Find matching words or consecutive word phrases in words.

    Matching is case-insensitive, ignores punctuation at the ends of words,
    and returns matches in order.
    """
    if not query or not query.strip() or not words:
        return []

    query_tokens = [_clean(w) for w in query.strip().split()]
    query_tokens = [q for q in query_tokens if q]
    if not query_tokens:
        return []

    norm_words = [_clean(str(w.get("w", ""))) for w in words]
    width = len(query_tokens)
    last_start = len(words) - width
    hits: list[dict[str, Any]] = []

    for i in range(last_start + 1):
        if norm_words[i : i + width] == query_tokens:
            first_w = words[i]
            last_w = words[i + width - 1]
            hits.append({
                "first": i,
                "last": i + width - 1,
                "start": float(first_w.get("start", 0.0)),
                "end": float(last_w.get("end", 0.0)),
            })

    return hits


def _merge_windows(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Filter zero-length/inverted windows and merge overlapping/adjacent intervals."""
    valid = [
        (float(s), float(e))
        for s, e in windows
        if float(e) > float(s)
    ]
    if not valid:
        return []

    valid.sort(key=lambda w: (w[0], w[1]))
    merged: list[tuple[float, float]] = []
    for s, e in valid:
        if not merged:
            merged.append((s, e))
        else:
            last_s, last_e = merged[-1]
            if s <= last_e:
                merged[-1] = (last_s, max(last_e, e))
            else:
                merged.append((s, e))
    return merged


def coverage(
    hit: dict[str, Any],
    windows: list[tuple[float, float]],
) -> str:
    """Calculate whether a hit span lies in, is cut from, or partly in windows.

    Returns:
        "in": the whole hit span lies inside the union of the windows.
        "cut": none of the hit span lies inside the union of the windows.
        "partly": otherwise.
    """
    h_start = float(hit.get("start", 0.0))
    h_end = float(hit.get("end", 0.0))
    if h_end <= h_start:
        return "cut"

    merged = _merge_windows(windows)
    if not merged:
        return "cut"

    # Check if completely inside any single merged window
    for s, e in merged:
        if s <= h_start + EPS and h_end <= e + EPS:
            return "in"

    # Calculate overlap
    overlap = 0.0
    for s, e in merged:
        inter_s = max(h_start, s)
        inter_e = min(h_end, e)
        if inter_e - inter_s > EPS:
            overlap += inter_e - inter_s

    if overlap <= EPS:
        return "cut"

    return "partly"
