"""Subtitles (SRT and WebVTT) from the timeline transcript.

Pure logic over the word dicts ``transcript.timeline_words`` returns: the
words are read, never changed, and nothing here touches a project, audio,
a file or the session. The wiring that hands the words in and writes the
file out comes later.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

#: The floor under a cue: anything shorter flashes by unreadably.
MIN_SECONDS = 0.5


@dataclass(frozen=True)
class Cue:
    """One subtitle cue.

    ``start`` and ``end`` are seconds on the timeline (floats), ``lines``
    the cue's text wrapped to lines, ``speaker`` the person id when one
    is mapped, else the raw ``spk`` label, empty when neither is set —
    a display name for an id is resolved where the people are known,
    the way ``/api/words`` does, not here.
    """

    start: float
    end: float
    lines: tuple[str, ...]
    speaker: str


def cues(words: list[dict], *, rate: int = 48_000, max_chars: int = 42,
         max_lines: int = 2, max_seconds: float = 6.0,
         gap_seconds: float = 1.0) -> tuple[Cue, ...]:
    """Group timeline words into subtitle cues.

    ``words`` are exactly ``transcript.timeline_words`` dicts, so ``s``
    and ``e`` are frames at the project rate: ``rate`` (the model's own
    default 48 000) converts them to the seconds the cues carry. Muted
    words — a muted clip or track, or a gate over them — are dropped,
    and a muted stretch is no gap between the kept words either: it is
    silence the subtitles simply sit over.

    A new cue starts at a speaker or track change, at a gap over
    ``gap_seconds`` between kept words, or when the next word would push
    the cue's text past ``max_chars * max_lines`` characters or its end
    past ``max_seconds``; a single word may exceed either rather than be
    split. Inside a cue the text wraps at word boundaries into lines at
    most ``max_chars`` wide.

    Every cue runs at least ``MIN_SECONDS``. When crosstalk starts the
    next cue sooner than that, the end stops at the next cue's start
    instead: never overlapping beats the floor, so a squeezed cue may
    fall short of it, down to nothing only when two cues share one
    start frame.
    """
    heard = sorted((w for w in words if not w.get("muted")),
                   key=lambda w: (w["s"], w["track"]))
    out: list[Cue] = []
    run: list[dict] = []
    key: tuple[str, str] | None = None
    chars = 0

    def flush() -> None:
        nonlocal run, chars
        if not run:
            return
        out.append(Cue(
            run[0]["s"] / rate,
            # A long early word can outlast a later short one, so the
            # cue ends with the latest end, not the last word's.
            max(w["e"] for w in run) / rate,
            _wrap([w["w"] for w in run], max_chars),
            _speaker(run[0]),
        ))
        run, chars = [], 0

    for w in heard:
        k = (_speaker(w), w["track"])
        if run and (k != key
                    or (w["s"] - run[-1]["e"]) / rate > gap_seconds
                    or chars + 1 + len(w["w"]) > max_chars * max_lines
                    or (w["e"] - run[0]["s"]) / rate > max_seconds):
            flush()
        if not run:
            key = k
            chars = len(w["w"])
        else:
            chars += 1 + len(w["w"])
        run.append(w)
    flush()

    # The words were in start order, so cue starts are non-decreasing:
    # each end clamps against the next start, and no cue moves.
    for i, c in enumerate(out):
        end = max(c.end, c.start + MIN_SECONDS)
        if i + 1 < len(out) and end > out[i + 1].start:
            end = out[i + 1].start
        out[i] = Cue(c.start, end, c.lines, c.speaker)
    return tuple(out)


def to_srt(cues: Iterable[Cue]) -> str:
    """The cues as SubRip text: numbered blocks, ``HH:MM:SS,mmm`` stamps,
    the speaker as a ``Name: `` prefix on the first line. An empty
    transcript is an empty file."""
    blocks = []
    for n, c in enumerate(cues, 1):
        lines = list(c.lines)
        if c.speaker:
            lines[0] = f"{c.speaker}: {lines[0]}"
        blocks.append("\n".join(
            [str(n), f"{_stamp(c.start, ',')} --> {_stamp(c.end, ',')}",
             *lines]))
    if not blocks:
        return ""
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: Iterable[Cue]) -> str:
    """The cues as WebVTT text: a ``WEBVTT`` header, ``HH:MM:SS.mmm``
    stamps, the speaker as a ``<v Name>`` tag on the first line. An empty
    transcript is the bare header."""
    blocks = []
    for c in cues:
        lines = list(c.lines)
        if c.speaker:
            lines[0] = f"<v {c.speaker}>{lines[0]}"
        blocks.append("\n".join(
            [f"{_stamp(c.start, '.')} --> {_stamp(c.end, '.')}", *lines]))
    if not blocks:
        return "WEBVTT\n"
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def _speaker(w: dict) -> str:
    # The resolved person is the speaker when one is mapped; the raw
    # label stands in until then (``people.resolve_words``).
    return w.get("person") or w.get("spk") or ""


def _wrap(texts: list[str], max_chars: int) -> tuple[str, ...]:
    """Greedy wrap at word boundaries; a word wider than ``max_chars``
    stands alone on its line rather than being split."""
    lines: list[str] = []
    cur: str | None = None
    for text in texts:
        if cur is None:
            cur = text
        elif len(cur) + 1 + len(text) <= max_chars:
            cur += " " + text
        else:
            lines.append(cur)
            cur = text
    if cur is not None:
        lines.append(cur)
    return tuple(lines)


def _stamp(seconds: float, separator: str) -> str:
    # Milliseconds first and divmod after, so a rounding that lands on a
    # whole second carries into the minutes instead of 00:00:60,000.
    total = round(seconds * 1000)
    hours, rest = divmod(total, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"
