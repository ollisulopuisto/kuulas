"""Map a recording to the clips and ranges that use it.

This is the backend for the inspector's "Source" view: given a recording,
where does the edit play it, which parts are heard, and which parts are left
out.
"""

from __future__ import annotations

from kuulas.clock import frames_to_flicks
from kuulas.model import Media, Project
from kuulas.usage import _audibility_ranges


def _resolve_recording(
    media: Media, media_by_id: dict[str, Media],
) -> tuple[str, int] | None:
    """Return (original_sha256, origin_flicks) for a media or its excerpt chain.

    Returns ``None`` when the chain is cyclic or the original is missing, so
    the caller treats the clip as belonging to no known recording.
    """
    origin = 0
    seen: set[str] = set()
    current = media
    while current.excerpt_of and current.excerpt_of != current.id:
        if current.id in seen:
            return None
        seen.add(current.id)
        origin += current.excerpt_start_flicks
        try:
            current = media_by_id[current.excerpt_of]
        except KeyError:
            return None
    return current.sha256, origin


def _track_index(project: Project, track_id: str) -> int:
    for index, track in enumerate(project.tracks):
        if track.id == track_id:
            return index
    raise KeyError(track_id)


def recording_clips(project: Project, media_sha256: str):
    """Clips playing ``media_sha256`` sorted by source start, then track order.

    Returns tuples of ``(track_id, clip_id, from_flicks, to_flicks, muted)``.
    ``muted`` is the clip's own ``muted`` flag.
    """
    media_by_id = {media.id: media for media in project.media}
    results = []
    for track in project.tracks:
        for clip in track.clips:
            media = media_by_id.get(clip.media)
            if media is None:
                continue
            resolved = _resolve_recording(media, media_by_id)
            if resolved is None:
                continue
            digest, origin = resolved
            if digest != media_sha256:
                continue
            from_flicks = origin + frames_to_flicks(clip.offset, project.rate)
            to_flicks = origin + frames_to_flicks(clip.offset + clip.length,
                                                  project.rate)
            results.append((track.id, clip.id, from_flicks, to_flicks,
                            clip.muted))
    results.sort(key=lambda item: (item[2], _track_index(project, item[0])))
    return results


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or touching ranges."""
    if not ranges:
        return []
    ordered = sorted(ranges)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _source_intervals(project: Project, media_sha256: str):
    """Return (audible_intervals, inaudible_intervals) for the recording."""
    media_by_id = {media.id: media for media in project.media}
    audible: list[tuple[int, int]] = []
    inaudible: list[tuple[int, int]] = []
    for track in project.tracks:
        for clip in track.clips:
            media = media_by_id.get(clip.media)
            if media is None:
                continue
            resolved = _resolve_recording(media, media_by_id)
            if resolved is None:
                continue
            digest, origin = resolved
            if digest != media_sha256:
                continue
            for timeline_from, timeline_to, is_audible in _audibility_ranges(track, clip):
                source_from = clip.offset + timeline_from - clip.start
                source_to = source_from + timeline_to - timeline_from
                from_flicks = origin + frames_to_flicks(source_from, project.rate)
                to_flicks = origin + frames_to_flicks(source_to, project.rate)
                if is_audible:
                    audible.append((from_flicks, to_flicks))
                else:
                    inaudible.append((from_flicks, to_flicks))
    return audible, inaudible


def _recording_length_flicks(project: Project, media_sha256: str) -> int | None:
    for media in project.media:
        if media.sha256 == media_sha256:
            return frames_to_flicks(media.frames, project.rate)
    return None


def coverage(project: Project, media_sha256: str):
    """Return ``(used, cut, unused)`` ranges on the recording's own clock.

    - ``used``: audible ranges (any non-muted, non-silenced clip).
    - ``cut``: covered only by inaudible clips (muted or ducked).
    - ``unused``: the rest of the recording, up to its media length.

    Each list is merged, sorted and disjoint.
    """
    length = _recording_length_flicks(project, media_sha256)
    if length is None:
        return [], [], []

    audible, inaudible = _source_intervals(project, media_sha256)
    used = _merge_ranges(audible)
    all_covered = _merge_ranges(audible + inaudible)

    # cut = covered ranges that are not used
    cut: list[tuple[int, int]] = []
    used_index = 0
    for cover_start, cover_end in all_covered:
        # Skip used ranges that end before or at this covered range
        while (used_index < len(used)
               and used[used_index][1] <= cover_start):
            used_index += 1
        current = cover_start
        while current < cover_end:
            if used_index < len(used) and used[used_index][0] < cover_end:
                u_start, u_end = used[used_index]
                if current < u_start:
                    cut.append((current, min(u_start, cover_end)))
                current = min(u_end, cover_end)
                if u_end <= current:
                    used_index += 1
            else:
                cut.append((current, cover_end))
                current = cover_end
    cut = _merge_ranges(cut)

    # unused = gaps in [0, length] outside all covered ranges
    unused: list[tuple[int, int]] = []
    current = 0
    for cover_start, cover_end in all_covered:
        if current < cover_start and current < length:
            unused.append((current, min(cover_start, length)))
        current = max(current, cover_end)
        if current >= length:
            break
    if current < length:
        unused.append((current, length))

    return used, cut, unused


def part_numbers(project: Project, media_sha256: str) -> dict[str, tuple[int, int]]:
    """Map each clip id playing the recording to ``(n, of)`` in source order."""
    clips = recording_clips(project, media_sha256)
    total = len(clips)
    return {
        clip_id: (index + 1, total)
        for index, (_track_id, clip_id, _from_flicks, _to_flicks, _muted)
        in enumerate(clips)
    }
