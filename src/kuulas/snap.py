"""Timeline snapping for mouse editing.

Pure functions that return candidate snap targets and resolve a frame to the
nearest target within a threshold.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable

from kuulas.model import Project

Kind = str


def _grid_targets(length: int, grid: int) -> Iterable[int]:
    """Multiples of ``grid`` from 0 up to and including ``length``."""
    if grid <= 0:
        return
    frame = 0
    while frame <= length:
        yield frame
        frame += grid


def snap_targets(
    project: Project,
    *,
    kinds: tuple[Kind, ...] = ("clip_edges", "playhead", "in_out", "grid"),
    playhead: int | None = None,
    in_out: tuple[int, int] | None = None,
    grid: int | None = None,
    exclude_clips: tuple[str, ...] = (),
) -> tuple[int, ...]:
    """Return a sorted, de-duplicated tuple of snap target frames."""
    excluded = set(exclude_clips)
    targets: set[int] = set()

    if "clip_edges" in kinds:
        for track in project.tracks:
            for clip in track.clips:
                if clip.id in excluded or clip.muted:
                    continue
                targets.add(clip.start)
                targets.add(clip.end)

    if "playhead" in kinds and playhead is not None:
        targets.add(playhead)

    if "in_out" in kinds and in_out is not None:
        targets.add(in_out[0])
        targets.add(in_out[1])

    if "grid" in kinds and grid is not None:
        targets.update(_grid_targets(project.length, grid))

    return tuple(sorted(targets))


def snap_to(
    frame: int, targets: tuple[int, ...], threshold: int,
) -> tuple[int, int | None]:
    """Snap ``frame`` to the nearest ``target`` within ``threshold`` frames.

    Ties go to the lower frame. If no target is within range, return
    ``(frame, None)``.
    """
    if not targets:
        return frame, None

    idx = bisect.bisect_left(targets, frame)
    candidates: list[int | None] = []
    if idx < len(targets):
        candidates.append(targets[idx])
    if idx > 0:
        candidates.append(targets[idx - 1])

    best_target: int | None = None
    best_distance = threshold + 1
    for target in candidates:
        if target is None:
            continue
        distance = abs(target - frame)
        if distance < best_distance or (
            distance == best_distance and target is not None
            and (best_target is None or target < best_target)
        ):
            best_target = target
            best_distance = distance

    if best_target is None or best_distance > threshold:
        return frame, None
    return best_target, best_target


def soft_snap(
    frame: int,
    targets: tuple[int, ...],
    threshold: int,
    hold_frames: int,
) -> tuple[int, int | None]:
    """Like ``snap_to``, but release the snap once the pointer has moved more
    than ``hold_frames`` past the target.
    """
    snapped, target = snap_to(frame, targets, threshold)
    if target is None:
        return frame, None
    if abs(frame - target) > hold_frames:
        return frame, None
    return snapped, target
