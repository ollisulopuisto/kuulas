"""What else a cut of transcript words would remove (crosstalk preview).

``Session``'s ``cut_words`` ripple-deletes the stretch the selected words
cover on every track, so cutting one speaker's words also takes whoever
spoke over them. This module computes that before the user commits: pure
logic over the project and its transcripts, no state changed. The
session and UI wiring comes later.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gate import normalise
from .model import Project
from .ops import EditError
from .transcript import timeline_words


@dataclass(frozen=True)
class Collateral:
    """What a cut of the selected words would also take.

    ``span``: the selected words' cover as one ``(start, end)`` frame range.
    ``other_words``: the words of the tracks the selection does not touch,
    inside the span, as the dicts ``timeline_words`` gives them, sorted by
    start. ``audio``: per other track, the merged unmuted clip ranges
    inside the span — the audio that would disappear with the words.
    """

    span: tuple[int, int]
    other_words: tuple[dict, ...]
    audio: dict[str, list[tuple[int, int]]]


def cut_collateral(project: Project, transcripts: dict[str, list[dict]],
                   selected: list[dict]) -> Collateral:
    """The collateral of cutting the words ``selected`` refers to.

    ``selected`` holds word refs as ``timeline_words`` identifies them (the
    ``track``, ``clip`` and ``index`` keys of its word dicts; other keys are
    ignored, so whole word dicts work as refs).

    The span is one range, from the first selected word's start to the last
    one's end, because the cut deletes one stretch: a disjoint selection
    loses the audio between its words too, and the preview must not hide
    that. A word is inside the span when it overlaps it by at least one
    frame; one that only touches an edge shares none. Muted clips and
    tracks contribute no audio; their words are still reported, with the
    ``muted`` flag ``timeline_words`` gives them.
    """
    words = timeline_words(project, transcripts)
    refs = {(r["track"], r["clip"], r["index"]) for r in selected}
    chosen = [w for w in words if (w["track"], w["clip"], w["index"]) in refs]
    if not chosen:
        # An empty or stale selection names no word to cut, exactly like
        # ``_cut_words`` with an empty index list.
        raise EditError("error.edit.no_selection")
    start = min(w["s"] for w in chosen)
    end = max(w["e"] for w in chosen)

    sel_tracks = {w["track"] for w in chosen}
    other_words = tuple(w for w in words
                        if w["track"] not in sel_tracks and w["s"] < end
                        and w["e"] > start)
    audio: dict[str, list[tuple[int, int]]] = {}
    for t in project.tracks:
        if t.id in sel_tracks:
            continue
        parts = [(max(c.start, start), min(c.end, end))
                 for c in t.clips if not (c.muted or t.mute)]
        parts = [part for part in parts if part[0] < part[1]]
        if parts:
            # Clips can overlap on a track; what disappears is the union.
            audio[t.id] = list(normalise(parts))
    return Collateral((start, end), other_words, audio)
