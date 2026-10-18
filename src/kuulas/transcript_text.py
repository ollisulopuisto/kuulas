"""The transcript as plain text and Markdown.

Pure logic over the word dicts ``transcript.timeline_words`` returns: the
words are read, never changed, and nothing here touches a project, audio,
a file or the session. The wiring that hands the words in and writes the
file out comes later.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Paragraph:
    """One paragraph of the transcript.

    ``start`` and ``end`` are seconds on the timeline (floats), ``text``
    the paragraph's words joined by single spaces, ``speaker`` the person
    id when one is mapped, else the raw ``spk`` label, empty when neither
    is set — a display name for an id is resolved where the people are
    known, the way ``/api/words`` does, not here.
    """

    start: float
    end: float
    text: str
    speaker: str


def paragraphs(words: list[dict], *, rate: int = 48_000,
              gap_seconds: float = 1.5) -> tuple[Paragraph, ...]:
    """Group timeline words into paragraphs.

    ``words`` are exactly ``transcript.timeline_words`` dicts, so ``s``
    and ``e`` are frames at the project rate: ``rate`` (the model's own
    default 48 000) converts them to the seconds the paragraphs carry.
    Muted words — a muted clip or track, or a gate over them — are
    dropped, and a muted stretch is no gap between the kept words
    either: it is silence the paragraph simply spans.

    A new paragraph starts at a speaker or track change or at a gap over
    ``gap_seconds`` between kept words.
    """
    heard = sorted((w for w in words if not w.get("muted")),
                   key=lambda w: (w["s"], w["track"]))
    out: list[Paragraph] = []
    run: list[dict] = []
    key: tuple[str, str] | None = None

    def flush() -> None:
        nonlocal run
        if not run:
            return
        out.append(Paragraph(
            run[0]["s"] / rate,
            # A long early word can outlast a later short one, so the
            # paragraph ends with the latest end, not the last word's.
            max(w["e"] for w in run) / rate,
            " ".join(w["w"] for w in run),
            _speaker(run[0]),
        ))
        run = []

    for w in heard:
        k = (_speaker(w), w["track"])
        if run and (k != key
                    or (w["s"] - run[-1]["e"]) / rate > gap_seconds):
            flush()
        if not run:
            key = k
        run.append(w)
    flush()
    return tuple(out)


def to_text(paragraphs: Iterable[Paragraph], *, timestamps: bool = True) -> str:
    """The paragraphs as plain text: a ``Speaker [h:mm:ss]`` header line,
    the paragraph's text on the next, a blank line between paragraphs.

    Without ``timestamps`` the header is the speaker alone; with neither
    a speaker nor a timestamp there is no header line, only the text. An
    empty transcript is empty text.
    """
    blocks = []
    for p in paragraphs:
        header = _header(p, timestamps)
        blocks.append("\n".join([header, p.text]) if header else p.text)
    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def to_markdown(paragraphs: Iterable[Paragraph]) -> str:
    """The paragraphs as Markdown: a ``**Speaker** (h:mm:ss)`` header
    line, the paragraph's text on the next, a blank line between
    paragraphs. Without a speaker the time stands in the parentheses
    alone. An empty transcript is empty text.
    """
    blocks = []
    for p in paragraphs:
        clock = _clock(p.start)
        head = (f"**{p.speaker}** ({clock})" if p.speaker
                else f"({clock})")
        blocks.append("\n".join([head, p.text]))
    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def _header(p: Paragraph, timestamps: bool) -> str:
    # The speaker leads when there is one, the time follows it or stands
    # alone; with neither there is no header line at all.
    if not timestamps:
        return p.speaker
    clock = _clock(p.start)
    return f"{p.speaker} [{clock}]" if p.speaker else f"[{clock}]"


def _speaker(w: dict) -> str:
    # The resolved person is the speaker when one is mapped; the raw
    # label stands in until then (``people.resolve_words``).
    return w.get("person") or w.get("spk") or ""


def _clock(seconds: float) -> str:
    # Seconds round and carry into the minutes and hours, so 59.7 s
    # prints 0:01:00, not 0:00:60; the hours are plain, the minutes and
    # seconds two wide.
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"
