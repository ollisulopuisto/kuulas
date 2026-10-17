"""File names for exported regions (WP19h, second part).

One file name per region, from the region's name, its 1-based position
and its start time, through a template, made safe for Mac, Windows and
Linux file systems and unique among the names already taken. Pure
string logic: no markers, no audio, no file I/O, no session wiring.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .messages import KuulasError

# Characters the three file systems refuse, plus Unicode control
# characters (Cc: the C0 block and DEL).
_BAD = set('/\\:*?"<>|')
_CONTROL = {"Cc"}

# Windows reserves these as the part before the first dot, whatever the
# extension ("CON.wav" cannot be created).
_RESERVED = ({"con", "prn", "aux", "nul"}
             | {f"com{i}" for i in range(1, 10)}
             | {f"lpt{i}" for i in range(1, 10)})

_SPACES = re.compile(r" +")
_MAX_CHARS = 120
_FALLBACK = "region"


def _stamp(seconds: float) -> str:
    """``seconds`` as ``hh-mm-ss``, whole seconds, zero-padded."""
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}-{minutes:02d}-{secs:02d}"


def _safe(stem: str) -> str:
    """``stem`` made safe as a file name's name part.

    Bad characters and controls are dropped, runs of spaces collapse to
    one, dots and spaces at the ends are stripped (Windows cannot have
    them), the stem is cut to ``_MAX_CHARS``, an empty result becomes
    ``_FALLBACK``, and a Windows-reserved part before the first dot gets
    an underscore after it, which changes that part, so ``NUL.5``
    becomes ``NUL_.5`` and not the still-reserved ``NUL.5_``.
    """
    kept = "".join(
        char for char in stem
        if char not in _BAD and unicodedata.category(char) not in _CONTROL)
    stem = _SPACES.sub(" ", kept).strip(" .")[:_MAX_CHARS] or _FALLBACK
    head, dot, rest = stem.partition(".")
    if head.casefold() in _RESERVED:
        stem = f"{head}_{dot}{rest}"
    return stem


def region_filenames(regions: Iterable[tuple[str, float]],
                     template: str = "{n:02d} {name}",
                     extension: str = "wav",
                     existing: Iterable[str] = ()) -> list[str]:
    """One safe file name per region, in order.

    ``regions`` holds ``(name, start_seconds)`` pairs. The template may
    use ``{n}`` (the 1-based position, honouring its format spec),
    ``{name}`` and ``{start}`` (the start as ``hh-mm-ss``); the rendered
    stem is then made safe as a whole, so a bad character in the
    template is caught too. A region's name is a value, never re-scanned
    for tokens, so a name that itself holds braces comes out as it is.
    A template with an unknown token, a positional index or a broken
    brace raises. The extension's leading dots are stripped; an empty
    extension means no dot at all. Two names never come out equal, case-
    insensitively as macOS and Windows file systems are: one that equals
    a name in ``existing`` or an earlier result gets `` 2``, `` 3``, ...
    before the extension.
    """
    ext = extension.lstrip(".")
    suffix = f".{ext}" if ext else ""
    taken = {name.casefold() for name in existing}
    names: list[str] = []
    for n, (name, start_seconds) in enumerate(regions, start=1):
        try:
            rendered = template.format(
                n=n, name=name, start=_stamp(start_seconds))
        except (KeyError, IndexError, ValueError):
            raise KuulasError("error.regions.bad_template",
                              template=template) from None
        stem = _safe(rendered)
        full = stem + suffix
        if full.casefold() in taken:
            # The counter starts at 2 and skips past whatever is taken.
            count = 2
            while full.casefold() in taken:
                full = f"{stem} {count}{suffix}"
                count += 1
        taken.add(full.casefold())
        names.append(full)
    return names
