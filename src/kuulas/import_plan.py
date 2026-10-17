"""Placement plan for importing several files (WP34-adjacent pure plan).

``Session.import_media`` already places one track per file by the recorders'
clock, or all files one after another on one track. This module is the same
logic as a pure plan, with the options the UI needs, and it is not wired in
yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .clock import flicks_to_frames
from .messages import KuulasError


@dataclass(frozen=True)
class ImportItem:
    """One file the user wants to import."""

    name: str
    frames: int
    channels: int
    time_ref_flicks: int | None = None
    person: str | None = None


@dataclass(frozen=True)
class Placement:
    """Where one item should go on the timeline."""

    item: ImportItem
    track_key: str
    track_name: str
    kind: str
    start_frame: int
    new_track: bool


def _kind(channels: int) -> str:
    return "music" if channels >= 2 else "speech"


def _track_name(item: ImportItem, track_naming: str) -> str:
    if track_naming == "person" and item.person:
        return item.person
    return Path(item.name).stem


def _natural_key(text: str) -> tuple:
    """Case-insensitive natural sort key: ``take2`` sorts before ``take10``."""
    parts: list = []
    current: list[str] = []
    current_is_digit: bool | None = None

    def flush() -> None:
        if current:
            joined = "".join(current)
            parts.append(int(joined) if current_is_digit else joined.lower())
            current.clear()

    for char in text:
        is_digit = char.isdigit()
        if current_is_digit is not None and is_digit != current_is_digit:
            flush()
        current.append(char)
        current_is_digit = is_digit
    flush()
    return tuple(parts)


def _order(items: tuple[ImportItem, ...], order: str) -> tuple[ImportItem, ...]:
    if order == "given":
        return items
    if order == "name":
        return tuple(sorted(items, key=lambda i: _natural_key(i.name)))
    # "time": items with a time reference first, then ties by name.
    return tuple(sorted(
        items,
        key=lambda i: (
            0 if i.time_ref_flicks is not None else 1,
            i.time_ref_flicks or 0,
            _natural_key(i.name),
        ),
    ))


def _validate_options(mode: str, order: str, track_naming: str) -> None:
    if mode not in ("side_by_side", "sequential"):
        raise KuulasError("error.import_plan.bad_mode", mode=mode)
    if order not in ("given", "name", "time"):
        raise KuulasError("error.import_plan.bad_order", order=order)
    if track_naming not in ("file", "person"):
        raise KuulasError("error.import_plan.bad_track_naming",
                          track_naming=track_naming)


def plan_import(
    items: tuple[ImportItem, ...] | list[ImportItem],
    rate: int,
    *,
    mode: str = "side_by_side",
    start_frame: int = 0,
    order: str = "given",
    track_naming: str = "file",
) -> tuple[Placement, ...]:
    """Return a placement plan for ``items``.

    - ``side_by_side``: one new track per item; start frame is
      ``start_frame + (time_ref - earliest_time_ref)`` converted to frames,
      or ``start_frame`` for an item with no time reference.
    - ``sequential``: one new track for all; each item starts where the
      previous ends, beginning at ``start_frame``; the track is named after
      the first item.
    - ``order``: ``"given"``, ``"name"`` (case-insensitive natural sort) or
      ``"time"`` (by time reference, items without one last, ties by name).
    - ``track_naming``: ``"file"`` (the file name without extension) or
      ``"person"`` (the item's person when it has one, else the file name).
    """
    _validate_options(mode, order, track_naming)
    ordered = _order(tuple(items), order)
    if not ordered:
        return ()

    if mode == "side_by_side":
        refs = [i.time_ref_flicks for i in ordered if i.time_ref_flicks is not None]
        earliest = min(refs) if refs else None
        placements = []
        for index, item in enumerate(ordered):
            if item.time_ref_flicks is None or earliest is None:
                start = start_frame
            else:
                delta = item.time_ref_flicks - earliest
                start = start_frame + flicks_to_frames(delta, rate)
            placements.append(Placement(
                item=item,
                track_key=f"t{index}",
                track_name=_track_name(item, track_naming),
                kind=_kind(item.channels),
                start_frame=start,
                new_track=True,
            ))
        return tuple(placements)

    # sequential
    track_key = "t0"
    track_name = _track_name(ordered[0], track_naming)
    track_kind = _kind(ordered[0].channels)  # one track, one kind: the first file's
    placements = []
    start = start_frame
    for index, item in enumerate(ordered):
        placements.append(Placement(
            item=item,
            track_key=track_key,
            track_name=track_name,
            kind=track_kind,
            start_frame=start,
            new_track=index == 0,
        ))
        start += item.frames
    return tuple(placements)
