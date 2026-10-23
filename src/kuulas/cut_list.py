"""The cut list: where the audio edit jumps, on the timeline and on the recording clock.

A video rough cut that follows a kuulas edit needs to know where the sound was cut, or
the picture shows a jump cut wherever the same camera carries on across a cut. Only kuulas
knows that (owner, 2026-10-23, ROADMAP "Final Cut XML in and out"). This is the plain
data: per speech track the cuts, and the places on the timeline where any track was cut
("seams").
Pure: a Project in, JSON-able data out. Nothing is read from or written to a recording.

A cut is a seam between two adjacent clips of a speech track whose recording clock jumps:
what was removed (or repeated, or reordered) between them. Clips with a gap between them
are not a cut (the track is silent there), nor is a split that removes nothing, nor is
muting. Frames are project-rate samples (``rate`` in the header).
"""

from __future__ import annotations

from itertools import pairwise

from . import ops
from .model import Clip, Project, Track

FORMAT = "kuulas-cut-list"
VERSION = 1


def _cut(p: Project, a: Clip, b: Clip) -> dict | None:
    """The cut between clip ``a`` and the clip ``b`` that follows it directly, or None."""
    group_a, group_b = p.sync_group(a.media), p.sync_group(b.media)
    if group_a is not None and group_b is not None and group_a.id == group_b.id:
        clock = group_a.id
        before = ops._recorded(p, a) + a.length
        after = ops._recorded(p, b)
    elif a.media == b.media:
        clock = None
        before, after = a.offset + a.length, b.offset
    else:
        # Unrelated recordings side by side: a cut, but nothing says what was removed.
        return {"at": b.start, "removed": None, "from": None, "to": None, "clock": None}
    if after == before:
        return None
    return {"at": b.start, "removed": after - before, "from": before, "to": after,
            "clock": clock}


def _track_cuts(p: Project, track: Track) -> list[dict]:
    clips = sorted(track.clips, key=lambda c: c.start)
    cuts = []
    for a, b in pairwise(clips):
        if b.start != a.start + a.length:
            continue
        found = _cut(p, a, b)
        if found is not None:
            cuts.append(found)
    return cuts


def _seams(tracks: list[dict]) -> list[dict]:
    """The timeline places where any track was cut, with the tracks that were."""
    by_place: dict[int, list[tuple[str, int | None]]] = {}
    for track in tracks:
        for cut in track["cuts"]:
            by_place.setdefault(cut["at"], []).append((track["id"], cut["removed"]))
    seams = []
    for at in sorted(by_place):
        found = by_place[at]
        removed = {r for _, r in found}
        seams.append({"at": at, "removed": removed.pop() if len(removed) == 1 else None,
                      "tracks": [tid for tid, _ in found]})
    return seams


def cut_list(p: Project) -> dict:
    """The cut list of ``p``: header, the recordings the speech tracks use (with the clock
    each is on), the speech tracks with their cuts, and the seams across tracks."""
    speech = [t for t in p.tracks if t.kind == "speech"]
    tracks = [{"id": t.id, "name": t.name, "speaker": t.speaker,
               "cuts": _track_cuts(p, t)} for t in speech]
    used = list(dict.fromkeys(c.media for t in speech for c in t.clips))
    media = []
    for media_id in used:
        try:
            item = p.media_item(media_id)
        except KeyError:
            continue
        member = p.sync_member(media_id)
        media.append({"id": item.id, "name": item.name, "sha256": item.sha256,
                      "clock": None if member is None else member[0].id,
                      "origin_flicks": None if member is None else member[1]})
    return {"format": FORMAT, "version": VERSION, "rate": p.rate, "length": p.length,
            "media": media, "tracks": tracks, "seams": _seams(tracks)}
