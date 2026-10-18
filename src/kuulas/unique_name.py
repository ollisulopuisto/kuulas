"""Unique names for new tracks and clips.

``unique_name(base, existing)`` returns ``base`` when it is free, otherwise
``base 2``, ``base 3`` and so on: the first name not already in ``existing``,
compared case-insensitively. A trailing space and number (``"Olli 2"``)
continues from that stem (``"Olli 3"``) rather than stacking (``"Olli 2 2"``).
Errors are plain ``ValueError``; there is no user-facing text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from itertools import count

_TRAILING_NUMBER = re.compile(r" (\d+)$")


def unique_name(base: str, existing: Iterable[str]) -> str:
    """Return a name not in ``existing``, compared case-insensitively.

    Returns ``base`` with surrounding whitespace stripped when it is free,
    otherwise ``base 2``, ``base 3`` ... the first free name. A trailing space
    and number continues from that stem. Raises ``ValueError`` for an empty
    base. ``existing`` is not mutated.
    """
    name = base.strip()
    if not name:
        msg = "base must not be empty"
        raise ValueError(msg)
    existing_lower = {existing_name.lower() for existing_name in existing}
    if name.lower() not in existing_lower:
        return name
    match = _TRAILING_NUMBER.search(name)
    if match:
        stem = name[: match.start()]
        number = int(match.group(1))
    else:
        stem = name
        number = 1
    for n in count(number + 1):
        candidate = f"{stem} {n}"
        if candidate.lower() not in existing_lower:
            break
    return candidate
