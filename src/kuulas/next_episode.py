"""Next-episode names, logic only (WP66).

``next_name`` bumps the LAST number in an episode name by one, keeping its
zero padding and growing the width when the number rolls over (e.g. "Episode
99" -> "Episode 100"). ``parse_episode`` splits a name around its last number.
Pure Python, stdlib only (``re``). Errors are plain ``ValueError``; there is
no user-facing text.
"""

from __future__ import annotations

import re

_DIGIT = re.compile(r"\d+")


def parse_episode(name: str) -> dict[str, str | int]:
    """Split ``name`` around its last number.

    Returns ``{"prefix", "number", "width", "suffix"}`` where ``width`` is the
    digit count of the matched number text. Raises ``ValueError`` when the
    name contains no digit.
    """
    matches = list(_DIGIT.finditer(name))
    if not matches:
        msg = f"no episode number in {name!r}"
        raise ValueError(msg)
    match = matches[-1]
    return {
        "prefix": name[: match.start()],
        "number": int(match.group()),
        "width": len(match.group()),
        "suffix": name[match.end() :],
    }


def next_name(name: str) -> str:
    """Return the name of the next episode.

    The last number in ``name`` is increased by one, keeping its zero padding
    (the width grows when the number rolls over, e.g. "Episode 99" ->
    "Episode 100"). Text before and after the number is kept unchanged. A
    name without any digit raises ``ValueError``.
    """
    parsed = parse_episode(name)
    next_number = str(parsed["number"] + 1).zfill(parsed["width"])
    return parsed["prefix"] + next_number + parsed["suffix"]
