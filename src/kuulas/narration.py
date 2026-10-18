"""Narration estimate (WP43).

Estimates how long narration text takes to read aloud, in timeline frames.
"""

from __future__ import annotations

import math
import re

from .messages import KuulasError

_WORD = re.compile(r"\w+(?:[-'\u2019.,]\w+)*", re.UNICODE)


def count_words(text: str) -> int:
    """Count narration words.

    Tokens such as ``e-mail``, ``don't`` and ``3.5`` count as one word, and
    punctuation at the ends is ignored. Unicode letters (``ä``, ``ö``, ``å``)
    count as word characters.
    """
    return len(_WORD.findall(text))


def estimate_frames(text: str, rate: int, words_per_second: float = 2.3) -> int:
    """Estimate the frames needed to narrate ``text``.

    ``words / words_per_second * rate`` rounded up, at least one second
    (``rate`` frames) when the text has at least one word, and ``0`` for empty
    or blank text. A ``words_per_second`` of zero or less raises a translated
    ``KuulasError``.
    """
    if words_per_second <= 0:
        raise KuulasError("error.narration.bad_words_per_second",
                          words_per_second=words_per_second)
    words = count_words(text)
    if words == 0:
        return 0
    return max(math.ceil((words / words_per_second) * rate), rate)


# -- the script for the narrator (WP43) ------------------------------------------

#: Words of the episode shown on each side of a line, so the narrator can hear
#: how it starts and where it lands.
CONTEXT_WORDS = 20


def clock(frames: int, rate: int) -> str:
    """``m:ss``, or ``h:mm:ss`` from an hour on."""
    seconds = int(frames // rate)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def script(project, words: list[dict]) -> list[dict]:
    """The placeholders in timeline order, each with its text, start, length
    and the ``CONTEXT_WORDS`` words that precede and follow it.

    ``words`` are ``transcript.timeline_words`` dicts (frames at the project
    rate); muted ones are not heard, so they are no context. "Before" are the
    words that end by the placeholder's start, "after" those that begin at or
    after its end (what plays on other tracks meanwhile is not around it).
    Without a transcript the context is empty.
    """
    rate = project.rate
    heard = sorted((w for w in words if not w.get("muted")),
                   key=lambda w: (w["s"], w["track"]))
    names = {t.id: t.name for t in project.tracks}
    out = []
    for h in sorted(project.placeholders, key=lambda h: (h.start, h.track, h.id)):
        before = [w["w"] for w in heard if w["e"] <= h.start][-CONTEXT_WORDS:]
        after = [w["w"] for w in heard if w["s"] >= h.end][:CONTEXT_WORDS]
        out.append({
            "id": h.id, "track": h.track, "track_name": names.get(h.track, h.track),
            "start": h.start, "time": clock(h.start, rate), "length": h.length,
            "seconds": round(h.length / rate), "estimated": h.estimated,
            "text": h.text, "language": h.language,
            "before": " ".join(before), "after": " ".join(after),
        })
    return out
