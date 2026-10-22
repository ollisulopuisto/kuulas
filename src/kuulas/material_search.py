"""Search every transcript of the project for words the edit does not play (T64).

The Transcript shows only what is heard, and Mod+F searches that. This finds the
rest: words that were cut away, sit under a muted clip or a closed gate, or belong
to a recording placed nowhere, each with the reason. Coverage comes from
``source_map.coverage`` (the used / cut / unused ranges of a recording on its own
clock), so there is one rule for what the edit plays, not two.
"""

from __future__ import annotations

from bisect import bisect_right

from . import source_map, transcript_find
from .clock import frames_to_flicks
from .model import Project
from .source_map import _resolve_recording
from .transcript import silent_tracks

#: Words of context either side of a hit, for the list under the find bar.
CONTEXT = 4

#: Reasons a word is not in the edit: ``cut`` (removed by a cut, a trim or never
#: reached), ``muted`` (a muted clip or track), ``gated`` (Auto-Silence closed it, or
#: the track is below -60 dB there), ``unused`` (its recording is placed nowhere).
IN, CUT, MUTED, GATED, UNUSED = "in", "cut", "muted", "gated", "unused"


def _inside(ranges: list[tuple[int, int]], point: int) -> bool:
    i = bisect_right(ranges, (point, float("inf"))) - 1
    return i >= 0 and ranges[i][0] <= point < ranges[i][1]


def _inaudible_reason(project: Project, silent: set[str], media_by: dict,
                      sha: str, point: int) -> str:
    """Why a covered but inaudible stretch is silent: a muted clip or track, else the
    gate. ``point`` is on the recording's clock (flicks)."""
    for track in project.tracks:
        for clip in track.clips:
            media = media_by.get(clip.media)
            resolved = _resolve_recording(media, media_by) if media else None
            if resolved is None or resolved[0] != sha:
                continue
            start = resolved[1] + frames_to_flicks(clip.offset, project.rate)
            end = resolved[1] + frames_to_flicks(clip.offset + clip.length,
                                                 project.rate)
            if start <= point < end:
                return MUTED if clip.muted or track.id in silent else GATED
    return MUTED


def search(project: Project, transcripts: dict[str, list[dict]],
           query: str) -> list[dict]:
    """The hits of ``query`` that are not (wholly) in the edit, recording by recording.

    Matching is the Transcript find's (``transcript_find.find``). A hit is
    ``{"media", "first", "last", "start", "end", "status", "partly", "before",
    "match", "after", "spk"}``: indices into the recording's words, its span in flicks
    from the recording's start, the reason (see ``IN`` .. ``UNUSED``; that of the first
    word the edit does not play), whether part of the phrase is still played, and the
    words around it. A recording the project does not know is skipped.
    """
    media_by = {m.id: m for m in project.media}
    silent = silent_tracks(project)
    coverage: dict[str, tuple[list, list, bool]] = {}
    out: list[dict] = []
    for media in project.media:
        words = transcripts.get(media.id)
        resolved = _resolve_recording(media, media_by)
        if not words or resolved is None:
            continue
        sha, origin = resolved
        matches = transcript_find.find(
            [{"w": w["w"], "track": media.id} for w in words], query)
        if not matches:
            continue
        if sha not in coverage:
            used, cut, _unused = source_map.coverage(project, sha)
            coverage[sha] = (used, cut, bool(used or cut))
        used, cut, placed = coverage[sha]
        for match in matches:
            states = []
            for i in match:
                point = origin + (words[i]["s"] + words[i]["e"]) // 2
                if _inside(used, point):
                    states.append(IN)
                elif _inside(cut, point):
                    states.append(
                        _inaudible_reason(project, silent, media_by, sha, point))
                else:
                    states.append(CUT if placed else UNUSED)
            if all(s == IN for s in states):
                continue
            first, last = match[0], match[-1]
            out.append({
                "media": media.id, "first": first, "last": last,
                "start": words[first]["s"], "end": words[last]["e"],
                "status": next(s for s in states if s != IN),
                "partly": IN in states,
                "before": " ".join(w["w"] for w in words[max(0, first - CONTEXT):first]),
                "match": " ".join(w["w"] for w in words[first:last + 1]),
                "after": " ".join(w["w"] for w in words[last + 1:last + 1 + CONTEXT]),
                "spk": words[first].get("spk", ""),
            })
    return out
