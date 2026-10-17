"""Chapter list formatter (WP19h).

Formats a sequence of ``(frame, title)`` pairs as either plain text
(``hh:mm:ss Title`` per line) or Podcasting 2.0 JSON. Chapters are sorted by
frame and titles are stripped.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from .messages import KuulasError

_TEXT_STYLE = "text"
_JSON_STYLE = "json"


def _stamp(frames: int, rate: int) -> str:
    """``frames`` at ``rate`` as ``hh:mm:ss`` with the seconds rounded down."""
    seconds = frames // rate
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_chapters(chapters: Iterable[tuple[int, str]],
                    rate: int,
                    style: str = "text") -> str:
    """Format ``chapters`` as text or Podcasting 2.0 JSON.

    ``chapters`` is a sequence of ``(frame, title)`` pairs where ``frame`` is a
    timeline frame at ``rate``. Returns a string ending with a newline.
    """
    if style not in (_TEXT_STYLE, _JSON_STYLE):
        raise KuulasError("error.chapters.unknown_style", style=style)

    items: list[tuple[int, str]] = []
    for frame, title in chapters:
        if frame < 0:
            raise KuulasError("error.chapters.negative_frame", frame=frame)
        stripped = title.strip()
        if not stripped:
            raise KuulasError("error.chapters.empty_title", frame=frame)
        items.append((frame, stripped))

    seen: set[int] = set()
    for frame, _title in items:
        if frame in seen:
            raise KuulasError("error.chapters.duplicate_frame", frame=frame)
        seen.add(frame)

    items.sort(key=lambda item: item[0])

    if style == _JSON_STYLE:
        payload = {
            "version": "1.2.0",
            "chapters": [
                {"startTime": round(frame / rate, 3), "title": title}
                for frame, title in items
            ],
        }
        return json.dumps(payload, ensure_ascii=False) + "\n"

    lines = [f"{_stamp(frame, rate)} {title}" for frame, title in items]
    return "\n".join(lines) + ("\n" if lines else "")
