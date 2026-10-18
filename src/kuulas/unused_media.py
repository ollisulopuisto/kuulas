"""Which imported recordings the edit never plays audibly (WP17 clip bin)."""

from __future__ import annotations

from bisect import bisect_left

from .model import Project
from .usage import Use, _recording, extract


def usage_summary(project: Project) -> dict[str, dict[str, int]]:
    """Per media id, how the edit uses it.

    ``{"clips": n, "audible_clips": n, "audible_flicks": total}``: clips
    placed on the timeline, clips with at least one audible range, and the
    total recording-clock span of those ranges in flicks. The audibility
    rules are ``usage.extract``'s own (a muted clip or track, automation
    below -60 dB, a closed gate), called here rather than restated.

    ``merge_gap=0`` keeps every use inside the clip that produced it: at
    extract's default 2-flick gap two touching pieces of one split merge
    into a single use whose start lies in the first piece only, and the
    second piece would look silent. Unmerged, a use maps back to exactly
    one clip — the one on that track whose span contains the use's timeline
    start and whose recording hash the use carries (clips on a track do not
    overlap, so the span alone identifies the clip; the hash check keeps
    the mapping true even if a resync ever lands two clips on one span).
    """
    uses = extract(project, merge_gap=0)
    starts: dict[str, list[int]] = {}
    audible: dict[str, list[Use]] = {}
    for use in uses:
        if use.audible:
            starts.setdefault(use.track, []).append(use.timeline_from)
            audible.setdefault(use.track, []).append(use)
    # extract() sorts by timeline start, so each per-track list is sorted too.
    media_by_id = {media.id: media for media in project.media}
    summary = {media.id: {"clips": 0, "audible_clips": 0, "audible_flicks": 0}
               for media in project.media}
    for track in project.tracks:
        track_starts = starts.get(track.id, [])
        track_uses = audible.get(track.id, [])
        for clip in track.clips:
            # extract() already raised for a clip whose media is unknown or
            # whose excerpt chain is broken, so the key and _recording hold.
            entry = summary[clip.media]
            entry["clips"] += 1
            digest, _origin = _recording(media_by_id[clip.media], media_by_id)
            lo = bisect_left(track_starts, clip.start)
            hi = bisect_left(track_starts, clip.end)
            own = [use for use in track_uses[lo:hi]
                   if use.media_sha256 == digest]
            if own:
                entry["audible_clips"] += 1
                entry["audible_flicks"] += sum(
                    use.to_flicks - use.from_flicks for use in own)
    return summary


def unused_media(project: Project) -> tuple[str, ...]:
    """Media ids, in ``project.media`` order, that no audible use plays.

    Unused means every placed clip of the media is inaudible — muted (the
    clip, its track, automation below -60 dB, or a closed gate covers it;
    extract's rules again), so nothing of it is heard — or no clip places
    it at all. The count is per media id: a recording whose excerpt alone
    plays stays unused here, because no clip references the original.
    """
    summary = usage_summary(project)
    return tuple(media.id for media in project.media
                 if summary[media.id]["audible_clips"] == 0)
