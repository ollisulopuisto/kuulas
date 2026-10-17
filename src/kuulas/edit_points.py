"""Edit points for the Tab key (WP19i).

Edit points are timeline frames that the playhead jumps to with Tab (next)
and Shift+Tab (previous). The mode (edges, transients, words) selects what
counts as an edit point:
- edges: start and end of every unmuted clip
- transients: onset detection on media, mapped through unmuted clips
- words: starts of words in the transcript, mapped through unmuted clips
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from typing import Any

from . import gate, onsets, transcript
from .messages import KuulasError
from .model import Project


class EditPointsError(KuulasError, ValueError):
    """The edit points request names an unknown mode."""


#: Edit point modes cycled by next_mode().
MODES: tuple[str, ...] = ("edges", "transients", "words")


def edit_points(
    project: Project,
    transcripts: dict[str, list[dict]],
    onsets_by_media: dict[str, Any],
    mode: str,
    track_id: str | None = None,
) -> list[int]:
    """Return sorted, de-duplicated timeline frames of the chosen mode.

    Modes:
    - ``"edges"``: start and end of every unmuted clip on unmuted tracks, plus
      the edges of the track's gate (WP44), minus clip edges inside it.
    - ``"transients"``: transient onsets mapped through clips.
    - ``"words"``: starts of transcript words on the track, skipping muted ones.

    If ``track_id`` is given, only edit points on that track are returned.
    """
    if mode not in MODES:
        raise EditPointsError("error.edit_points.unknown_mode", mode=mode)

    if mode == "edges":
        points: list[int] = []
        for track in project.tracks:
            if track_id is not None and track.id != track_id:
                continue
            if track.mute:
                continue
            for clip in track.clips:
                if clip.muted:
                    continue
                # A clip edge inside a closed gate range is not an audible
                # edge; the gate's own edges are, where they lie in the clip.
                points.extend(edge for edge in (clip.start, clip.end)
                              if not gate.closed_at(track.gate, edge))
                points.extend(
                    edge for a, b in track.gate for edge in (a, b)
                    if clip.start <= edge <= clip.end)
        return sorted(set(points))

    if mode == "transients":
        return onsets.timeline_onsets(project, onsets_by_media, track_id=track_id)

    if mode == "words":
        words = transcript.timeline_words(project, transcripts)
        starts: list[int] = []
        for w in words:
            if w.get("muted"):
                continue
            if track_id is not None and w.get("track") != track_id:
                continue
            starts.append(w["s"])
        return sorted(set(starts))

    raise EditPointsError("error.edit_points.unknown_mode", mode=mode)


def next_point(points: Sequence[int], frame: int) -> int | None:
    """Return the nearest edit point strictly after ``frame``, or None at the end."""
    idx = bisect.bisect_right(points, frame)
    return points[idx] if idx < len(points) else None


def previous_point(points: Sequence[int], frame: int) -> int | None:
    """Return the nearest edit point strictly before ``frame``, or None at the start."""
    idx = bisect.bisect_left(points, frame)
    return points[idx - 1] if idx > 0 else None


def next_mode(mode: str) -> str:
    """Cycle edit point modes: edges -> transients -> words -> edges."""
    if mode not in MODES:
        raise EditPointsError("error.edit_points.unknown_mode", mode=mode)
    idx = MODES.index(mode)
    return MODES[(idx + 1) % len(MODES)]
