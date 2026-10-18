"""Excerpts of media for copying clips between projects (WP20).

Copying a clip to another project copies only the part of the media it plays,
plus handles on each side. All media positions are whole frames at ``rate``;
word timestamps are flicks (1 second = 705600000 flicks).
"""

from __future__ import annotations

FLICKS_PER_SECOND = 705_600_000


def excerpt_window(
    ranges: list[tuple[int, int]],
    handle_seconds: float,
    rate: int,
    media_frames: int,
) -> tuple[int, int]:
    """Return the union of ``ranges`` widened by ``handle_seconds`` each side.

    ``ranges`` are inclusive ``(first_frame, last_frame)`` source ranges. The
    result is clamped to ``[0, media_frames]``. Raises ``ValueError`` for
    empty ``ranges``.
    """
    if not ranges:
        msg = "excerpt_window: ranges must not be empty"
        raise ValueError(msg)
    handle_frames = int(handle_seconds * rate)
    start = min(first for first, _ in ranges) - handle_frames
    end = max(last for _, last in ranges) + handle_frames
    return max(0, start), min(media_frames, end)


def shift_offset(offset: int, excerpt_start: int) -> int:
    """Return ``offset - excerpt_start``.

    Raises ``ValueError`` when the result would be negative.
    """
    result = offset - excerpt_start
    if result < 0:
        msg = f"offset {offset} is negative relative to excerpt start {excerpt_start}"
        raise ValueError(msg)
    return result


def flicks(frames: int, rate: int) -> int:
    """Convert ``frames`` at ``rate`` to flicks using integer maths."""
    return frames * FLICKS_PER_SECOND // rate


def slice_words(
    words: list[dict],
    start_flicks: int,
    end_flicks: int,
) -> list[dict]:
    """Return copies of the words whose midpoint lies in ``[start, end)``.

    Each kept word has ``s`` and ``e`` shifted by ``-start_flicks``. The input
    list and its dicts are not mutated.
    """
    kept: list[dict] = []
    for word in words:
        midpoint = (word["s"] + word["e"]) // 2
        if start_flicks <= midpoint < end_flicks:
            shifted = dict(word)
            shifted["s"] = word["s"] - start_flicks
            shifted["e"] = word["e"] - start_flicks
            kept.append(shifted)
    return kept


def excerpt_origin(original_origin_flicks: int, start_flicks: int) -> int:
    """Return the excerpt's sync origin: the original origin plus the start."""
    return original_origin_flicks + start_flicks
