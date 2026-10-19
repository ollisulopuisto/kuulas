"""A chapter list from markers, for show notes.

``chapter_lines`` takes a project's markers as plain
``{"frame": int, "name": str}`` dicts (any order; ``frame`` in frames at
``rate``) and the programme length in frames, and returns the
``"<time> <name>"`` lines show notes need. Markers outside the programme
(``frame`` negative or at or past ``programme_length``) and unnamed markers
are skipped; the rest are sorted by frame and one line is kept per second
(``frame // rate``): the first marker of a second, by frame then by input
order. Time is ``M:SS`` under one hour (minutes not zero padded) and
``H:MM:SS`` from one hour on, with the seconds floored. A programme whose
first kept marker is past the first second starts with ``"0:00 Intro"``
(the fixed word this list format is known by, not a translated string).
When nothing is kept there is no first kept marker and the list is empty.

``chapter_text`` joins the lines for a text export.

Pure Python, stdlib only, no kuulas imports, no I/O. Errors are plain
``ValueError`` with no user-facing text. No input is ever touched.
"""

from __future__ import annotations

#: The line a programme starts with when its first kept marker is not at
#: second 0: show notes list the programme from the start, so the stretch
#: before the first named chapter still gets a line.
_INTRO_LINE = "0:00 Intro"


def _format_seconds(seconds: int) -> str:
    """``seconds`` as show-notes time: ``M:SS`` under an hour, ``H:MM:SS`` on.

    Minutes are not zero padded below an hour ("4:07"); from one hour on
    the hours are not padded and the minutes are ("1:02:09").
    """
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def chapter_lines(markers: list[dict], rate: int, programme_length: int) -> list[str]:
    """Return the show-notes chapter lines for ``markers``.

    ``markers`` is a list of ``{"frame": int, "name": str}`` dicts in any
    order, ``frame`` in frames at ``rate``; ``programme_length`` is the
    programme's length in frames. The return is a list of
    ``"<time> <name>"`` strings, one per second the kept markers hit,
    sorted by frame, each line's time floored to the second.

    A marker is skipped when its frame is negative or at or past
    ``programme_length``, or when its name is empty after stripping. Two
    kept markers in the same second keep the first: the smaller frame,
    then the earlier input. When the first kept marker is not at second 0
    the list starts with ``"0:00 Intro"``; when nothing is kept the list
    is empty.

    Raises ``ValueError`` when ``rate`` is not positive or
    ``programme_length`` is negative. The inputs are never mutated.
    """
    if rate <= 0:
        msg = f"rate must be positive, got {rate}"
        raise ValueError(msg)
    if programme_length < 0:
        msg = f"programme_length must not be negative, got {programme_length}"
        raise ValueError(msg)

    kept: list[tuple[int, int, str]] = []
    for index, item in enumerate(markers):
        frame = item["frame"]
        name = item["name"].strip()
        if frame < 0 or frame >= programme_length:
            continue
        if not name:
            continue
        # (frame, index): a stable sort by frame keeps the input order for
        # equal frames, which is the second tiebreak the format needs.
        kept.append((frame, index, name))
    kept.sort()

    lines: list[str] = []
    if kept and kept[0][0] // rate > 0:
        # The programme starts before its first named chapter.
        lines.append(_INTRO_LINE)
    previous_second: int | None = None
    for frame, _index, name in kept:
        second = frame // rate
        if second == previous_second:
            continue  # the first marker of this second already made its line
        previous_second = second
        lines.append(f"{_format_seconds(second)} {name}")
    return lines


def chapter_text(lines: list[str]) -> str:
    """The chapter lines as one text: joined with ``"\\n"``, ``""`` when empty."""
    return "\n".join(lines)
