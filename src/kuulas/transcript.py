"""The transcript as a view of the timeline.

Words are stored per media in flicks from the media's start, on the
recording clock (``{"w", "s", "e", "spk"}``), and never edited by audio
edits or by a change of project rate; they are converted to frames here.
Their timeline positions are derived from the clips every time, so moving,
trimming or cutting audio moves the text with it, and deleting text is a
ripple cut computed here.
"""

from __future__ import annotations

from .clock import flicks_to_frames
from .gate import closed_at
from .model import Project


def silent_tracks(p: Project) -> set[str]:
    """The tracks nobody hears, by the mixer's rule: while anything is soloed
    only soloed tracks play (muted or not), otherwise muted tracks do not; and
    a muted bus silences every track on it."""
    soloing = any(t.solo for t in p.tracks)
    muted_buses = {b.id for b in p.buses if b.mute}
    return {t.id for t in p.tracks
            if (not t.solo if soloing else t.mute) or t.bus in muted_buses}


def timeline_words(p: Project, transcripts: dict[str, list[dict]]) -> list[dict]:
    """Every word some clip plays, on the timeline, in time order.

    A word belongs to the clip that plays its midpoint, so a cut through a
    word shows it once, on the side that keeps most of it.
    """
    out = []
    silent = silent_tracks(p)
    for track in p.tracks:
        for clip in track.clips:
            words = transcripts.get(clip.media)
            if not words:
                continue
            lo, hi = clip.offset, clip.offset + clip.length
            shift = clip.start - clip.offset
            for i, w in enumerate(words):
                s = flicks_to_frames(w["s"], p.rate)
                e = max(s + 1, flicks_to_frames(w["e"], p.rate))
                mid = (s + e) // 2
                if lo <= mid < hi:
                    # A word is gated when its midpoint is: the same
                    # rule that decides which clip owns it.
                    gated = closed_at(track.gate, mid + shift) if track.gate else False
                    out.append({
                        "w": w["w"], "spk": w.get("spk", ""),
                        "person": w.get("person", ""),
                        "s": max(clip.start, s + shift),
                        "e": min(clip.end, e + shift),
                        "track": track.id, "clip": clip.id, "media": clip.media,
                        "index": i, "muted": clip.muted or track.id in silent or gated,
                    })
    out.sort(key=lambda w: (w["s"], w["track"]))
    return out


def cut_range(words: list[dict], selected: list[int]) -> tuple[int, int]:
    """Timeline range to ripple-delete for the selected words (indices into ``words``).

    Each side cuts to the middle of the pause to the neighbouring word, so
    what is left is one natural pause, not two halves of nothing and not a
    clipped consonant. At the ends of the programme it cuts to the word itself.
    """
    first = min(words[i]["s"] for i in selected)
    last = max(words[i]["e"] for i in selected)
    before = [w["e"] for w in words if w["e"] <= first]
    after = [w["s"] for w in words if w["s"] >= last]
    a = (max(before) + first) // 2 if before else first
    b = (last + min(after)) // 2 if after else last
    return a, b
