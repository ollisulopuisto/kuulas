"""Stable recording ranges used by reports, series and change comparisons."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

from . import gate as gatem
from .clock import FLICKS, frames_to_flicks
from .curves import value_at
from .messages import KuulasError
from .model import Clip, Media, Project, Track

AUDIBLE_DB = -60.0
DEFAULT_MERGE_GAP = 2 * FLICKS


class UsageError(KuulasError, ValueError):
    """Invalid or incomplete project material for usage extraction."""


@dataclass(frozen=True, order=True)
class Use:
    """One used stretch of a recording, mapped to its original content clock."""

    media_sha256: str
    from_flicks: int
    to_flicks: int
    timeline_from: int
    timeline_to: int
    track: str
    role: str
    audible: bool


def _recording(media: Media, media_by_id: dict[str, Media]) -> tuple[str, int]:
    """Return original hash and frame-zero clock offset for nested excerpts."""
    origin = 0
    seen: set[str] = set()
    current = media
    while current.excerpt_of and current.excerpt_of != current.id:
        if current.id in seen:
            raise UsageError("error.usage.excerpt_cycle", media_id=current.id)
        seen.add(current.id)
        origin += current.excerpt_start_flicks
        try:
            current = media_by_id[current.excerpt_of]
        except KeyError as error:
            raise UsageError("error.usage.excerpt_missing", media_id=current.id,
                             original_id=current.excerpt_of) from error
    return current.sha256, origin


def _audibility_ranges(track: Track, clip: Clip) -> list[tuple[int, int, bool]]:
    """Split a clip where track automation falls below -60 dB or the track's
    gate is closed (WP44: a gated stretch is inaudible, as a muted clip is)."""
    start, end = clip.start, clip.end
    if clip.muted or track.mute:
        return [(start, end, False)]
    ranges = _automation_ranges(track, clip)
    clip_gate = gatem.normalise(
        (clip.start + max(a, clip.offset) - clip.offset,
         clip.start + min(b, clip.offset + clip.length) - clip.offset)
        for a, b in clip.auto_silence
        if min(b, clip.offset + clip.length) > max(a, clip.offset))
    if not track.gate and not clip_gate:
        return ranges
    out: list[tuple[int, int, bool]] = []
    for left, right, audible in ranges:
        track_pieces = (gatem.split_by_gate(track.gate, left, right) if track.gate
                        else [(left, right, True)])
        for track_left, track_right, track_open in track_pieces:
            clip_pieces = (gatem.split_by_gate(clip_gate, track_left, track_right)
                           if clip_gate else [(track_left, track_right, True)])
            out.extend((a, b, audible and track_open and clip_open)
                       for a, b, clip_open in clip_pieces)
    return out


def _automation_ranges(track: Track, clip: Clip) -> list[tuple[int, int, bool]]:
    start, end = clip.start, clip.end
    if not track.automation:
        return [(start, end, True)]

    points = track.automation
    boundaries = {start, end}
    boundaries.update(frame for frame, _db in points if start < frame < end)
    knots = sorted(boundaries)
    for left, right in pairwise(knots):
        left_db = value_at(points, left)
        right_db = value_at(points, right)
        left_below = left_db < AUDIBLE_DB
        right_below = right_db < AUDIBLE_DB
        if left_below != right_below and left_db != right_db:
            crossing = left + (AUDIBLE_DB - left_db) * (right - left) / (
                right_db - left_db)
            boundary = math.ceil(crossing) if left_below else math.floor(crossing) + 1
            if left < boundary < right:
                boundaries.add(boundary)

    ordered = sorted(boundaries)
    ranges = []
    for left, right in pairwise(ordered):
        midpoint = (left + right - 1) // 2
        ranges.append((left, right, value_at(points, midpoint) >= AUDIBLE_DB))
    return ranges


def _merge(uses: list[Use], *, merge_gap: int, rate: int) -> list[Use]:
    """Merge same-source, same-lane ranges close in both clocks."""
    ordered = sorted(uses, key=lambda use: (
        use.media_sha256, use.track, use.role, use.audible, use.from_flicks,
        use.timeline_from, use.to_flicks,
    ))
    merged: list[Use] = []
    for use in ordered:
        if merged:
            previous = merged[-1]
            source_gap = use.from_flicks - previous.to_flicks
            timeline_gap = frames_to_flicks(
                use.timeline_from - previous.timeline_to, rate)
            same_use = (use.media_sha256, use.track, use.role, use.audible) == (
                previous.media_sha256, previous.track, previous.role, previous.audible)
            if same_use and 0 <= source_gap < merge_gap and 0 <= timeline_gap < merge_gap:
                merged[-1] = Use(
                    previous.media_sha256,
                    previous.from_flicks,
                    max(previous.to_flicks, use.to_flicks),
                    previous.timeline_from,
                    max(previous.timeline_to, use.timeline_to),
                    previous.track,
                    previous.role,
                    previous.audible,
                )
                continue
        merged.append(use)
    return merged


def extract(project: Project, *, merge_gap: int = DEFAULT_MERGE_GAP) -> tuple[Use, ...]:
    """Extract stable source-clock uses from one project state.

    ``merge_gap`` is measured in flicks. A gap is merged only when it is
    shorter than the limit in both recording time and timeline time, and the
    clips share their track, role and audibility.
    """
    if merge_gap < 0:
        raise UsageError("error.usage.bad_merge_gap", merge_gap=merge_gap)
    media_by_id = {media.id: media for media in project.media}
    uses = []
    for track in project.tracks:
        for clip in track.clips:
            media = media_by_id.get(clip.media)
            if media is None:
                raise UsageError("error.usage.media_missing", clip_id=clip.id,
                                 media_id=clip.media)
            digest, origin = _recording(media, media_by_id)
            for timeline_from, timeline_to, audible in _audibility_ranges(track, clip):
                source_from = clip.offset + timeline_from - clip.start
                source_to = source_from + timeline_to - timeline_from
                uses.append(Use(
                    digest,
                    origin + frames_to_flicks(source_from, project.rate),
                    origin + frames_to_flicks(source_to, project.rate),
                    timeline_from,
                    timeline_to,
                    track.id,
                    track.kind,
                    audible,
                ))
    merged = _merge(uses, merge_gap=merge_gap, rate=project.rate)
    return tuple(sorted(merged, key=lambda use: (
        use.timeline_from, use.timeline_to, use.track, use.media_sha256,
        use.from_flicks, use.audible,
    )))
