"""Narration estimate (WP43).

Estimates how long narration text takes to read aloud, in timeline frames.
"""

from __future__ import annotations

import math
import re

from .messages import KuulasError

_WORD = re.compile(r"\w+(?:[-'’.,]\w+)*", re.UNICODE)


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
