"""Names for takes.

``take_name`` numbers a new take after the takes already in use,
``file_stem`` builds a file stem from a take and a track name,
``timestamp_stem`` stamps a stem with a datetime, and
``unique_file_names`` makes stems unique as file names. Errors are plain
``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

import re
from datetime import datetime

from kuulas.safe_filename import safe_filename
from kuulas.unique_name import unique_name

_TAKE = re.compile(r"take\s+(\d+)", re.IGNORECASE)


def _require_string(value: object, what: str) -> str:
    if not isinstance(value, str):
        msg = f"{what} must be a string"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError
    return value


def take_name(existing: list[str], when: datetime) -> str:  # noqa: ARG001 - the clock is the caller's concern
    """Return ``"Take N"`` with N one above the highest take number in use.

    Existing names of the form ``"Take <n>"`` count, case-insensitively,
    with any text after the number ignored (``"take 7 (bad)"`` counts as 7).
    Returns ``"Take 1"`` when none are in use.
    """
    highest = 0
    for name in existing:
        _require_string(name, "a take name")
        match = _TAKE.match(name)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"Take {highest + 1}"


def file_stem(take: str, track_name: str) -> str:
    """Return the file stem ``"<take> <track>"``, made safe (max 80 chars).

    An empty track name leaves just the take.
    """
    _require_string(take, "take")
    _require_string(track_name, "track name")
    if not track_name:
        return take
    return safe_filename(f"{take} {track_name}", max_len=80)


def timestamp_stem(when: datetime) -> str:
    """Return ``"YYYY-MM-DD HHMMSS"`` from ``when``'s own fields, 24-hour."""
    return (
        f"{when.year:04d}-{when.month:02d}-{when.day:02d} "
        f"{when.hour:02d}{when.minute:02d}{when.second:02d}"
    )


def unique_file_names(stems: list[str], existing_files: list[str]) -> list[str]:
    """Return the stems with ``".wav"`` added, unique against ``existing_files``.

    Uniqueness is case-insensitive, using :func:`unique_name` on each stem,
    in the given order, so stems already returned count as taken. Neither
    input is mutated.
    """
    for stem in stems:
        _require_string(stem, "a stem")
    for existing in existing_files:
        _require_string(existing, "an existing file name")
    used = {name.lower() for name in existing_files}
    result: list[str] = []
    for stem in stems:
        name = unique_name(stem + ".wav", used)
        used.add(name.lower())
        result.append(name)
    return result
