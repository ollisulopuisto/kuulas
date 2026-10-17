"""Join adjacent clips that form one continuous piece of source media."""

from __future__ import annotations

from kuulas.model import Clip


def join_adjacent(clips: list[Clip]) -> list[Clip]:
    """Return ``clips`` with every joinable run merged into a single clip.

    Two clips are joined when they are the same media, contiguous both on the
    timeline and in the source, and share the same gain, pan and mute state,
    and have no envelope or crossfade at the boundary. The first clip's id and
    ``fade_in`` are kept, the last clip's ``fade_out`` is kept, and the length
    is the total. The result is sorted by timeline start and the input list is
    not modified.
    """
    if not clips:
        return []

    ordered = sorted(clips, key=lambda clip: clip.start)
    merged: list[Clip] = [ordered[0]]

    for current in ordered[1:]:
        previous = merged[-1]
        if _can_join(previous, current):
            merged[-1] = _join_two(previous, current)
        else:
            merged.append(current)

    return merged


def _can_join(a: Clip, b: Clip) -> bool:
    return (
        a.media == b.media
        and a.offset + a.length == b.offset
        and a.end == b.start
        and a.gain_db == b.gain_db
        and a.pan == b.pan
        and a.muted == b.muted
        and a.envelope == ()
        and b.envelope == ()
        and a.xfade_out == 0
        and b.xfade_in == 0
    )


def _join_two(a: Clip, b: Clip) -> Clip:
    return Clip(
        id=a.id,
        media=a.media,
        start=a.start,
        offset=a.offset,
        length=a.length + b.length,
        gain_db=a.gain_db,
        pan=a.pan,
        fade_in=a.fade_in,
        fade_out=b.fade_out,
        muted=a.muted,
        envelope=(),
        xfade_in=a.xfade_in,
        xfade_out=b.xfade_out,
        extra=a.extra,
    )
