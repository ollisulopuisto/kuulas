"""The transcript words inside a clipboard entry (WP65 step 2).

An entry keeps the words the copied stretch contains as plain text, so the
Clipboard tab can search what was *said* in a clip without opening the project
it came from, or the audio. Pure: the caller hands over the transcripts.
"""

from __future__ import annotations

from .clipboard import Entry
from .clock import flicks_to_frames
from .model import Project


def entry_text(project: Project, entry: Entry,
               transcripts: dict[str, list[dict]]) -> str:
    """The words of ``entry`` as text: one line per source track (in track
    order), each its clips' words in time order, joined with single spaces.

    ``transcripts`` is media id -> words (flicks from the media's start, the
    form ``Session.transcripts`` returns). A word belongs to a clip when its
    midpoint lies in the clip's window of the recording, the rule the
    transcript view uses (``transcript.timeline_words``), so a word cut
    through is counted once. Media the project does not have, or without a
    transcript, add nothing; an entry with no words at all gives "".
    """
    media_of = {m.sha256: m.id for m in project.media}
    lines: dict[int, list[tuple[int, int, str]]] = {}
    for ref in entry.refs:
        words = transcripts.get(media_of.get(ref.media_sha256, ""))
        if not words:
            continue
        lo, hi = ref.offset, ref.offset + ref.length
        for word in words:
            start = flicks_to_frames(word["s"], project.rate)
            end = max(start + 1, flicks_to_frames(word["e"], project.rate))
            text = str(word.get("w", "")).strip()
            if text and lo <= (start + end) // 2 < hi:
                lines.setdefault(ref.track_slot, []).append(
                    (ref.rel_start + (start - lo), ref.rel_start, text))
    return "\n".join(
        " ".join(text for _, _, text in sorted(lines[slot], key=lambda w: w[:2]))
        for slot in sorted(lines))
