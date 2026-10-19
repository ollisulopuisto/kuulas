"""Matching a template's recording names against a folder's files (WP66), logic only.

A template clip names its recording by file name (``media``); when the
template is used, its recordings are looked for in a folder.
``match_media`` takes the wanted names (from the template) and the
available names (a folder's listing, names only, no paths) and reports,
per wanted name, the available name it matches — or lists it as missing.

A match is the same name ignoring case, accents (NFKD, combining marks
dropped) and surrounding whitespace; failing that, the same stem (the name
without its last extension) matched against an available name that ends in
an audio extension, so a recording that moved between formats between
episodes still finds its file: "jingle.wav" finds "Jingle.flac". When
several available names match, the exact-case one is preferred (the whole
name in the first stage, the stem in the second), then the first in
``available`` order.

Pure Python, stdlib only, no kuulas imports, no I/O. Errors are plain
``ValueError`` with no user-facing text. No input is ever touched.
"""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath

#: The extensions an available name may carry for the stem match. The
#: whole-name match has no extension rule: a template names a recording by
#: its real name, whatever it ends in.
_AUDIO_EXTENSIONS = frozenset(
    {"wav", "flac", "mp3", "m4a", "aif", "aiff", "ogg", "opus"}
)


def _key(name: str) -> str:
    """The comparison key of a name: case, accents and edge whitespace off.

    Inner whitespace stays: only the surrounding whitespace is ignored, so
    "my file.wav" and "my  file.wav" remain different names.
    """
    decomposed = unicodedata.normalize("NFKD", name.strip())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return plain.casefold()


def _stem(name: str) -> str:
    """The name without its last extension, on the whitespace-stripped name.

    pathlib keeps whitespace and drops only the last extension ("a.b.wav"
    has the stem "a.b", dotfiles none), so stripping first keeps an edge
    space out of the stem and the extension.
    """
    return PurePosixPath(name.strip()).stem


def _extension(name: str) -> str:
    """The last extension without its dot, case-folded."""
    return PurePosixPath(name.strip()).suffix[1:].casefold()


def _require_str(name, side: str) -> None:
    if not isinstance(name, str):
        msg = f"{side} name must be a string, got {name!r}"
        raise ValueError(msg)  # noqa: TRY004 - the contract is plain ValueError


def match_media(wanted: list[str], available: list[str]) -> dict:
    """Return which available names the wanted names match.

    ``wanted`` are the file names a template's clips name their recordings
    by, ``available`` the file names a folder holds (names only, no paths).
    The return is ``{"found": {wanted_name: available_name}, "missing":
    [wanted_name, ...]}``: every key and value the raw spelling it was
    given, ``missing`` in ``wanted`` order (first occurrence).

    Two wanted names that are the same by the matching rules (case,
    accents, surrounding whitespace) report once, under the first spelling
    given. Two different wanted names may find the same available name:
    the preference rules run per wanted name, nothing is consumed.

    Raises ``ValueError`` when a name in ``wanted`` or ``available`` is not
    a string. The inputs are never mutated.
    """
    for name in wanted:
        _require_str(name, "wanted")
    for name in available:
        _require_str(name, "available")

    by_name: dict[str, list[str]] = {}
    by_stem: dict[str, list[str]] = {}
    for name in available:
        by_name.setdefault(_key(name), []).append(name)
        if _extension(name) in _AUDIO_EXTENSIONS:
            by_stem.setdefault(_key(_stem(name)), []).append(name)

    found: dict[str, str] = {}
    missing: list[str] = []
    seen: set[str] = set()
    for name in wanted:
        key = _key(name)
        if key in seen:
            continue  # a duplicate wanted name reports once, first spelling
        seen.add(key)
        if names := by_name.get(key):
            # Prefer the exact-case one, then the first in available order.
            found[name] = next((c for c in names if c == name), names[0])
        elif stems := by_stem.get(_key(_stem(name))):
            stem = _stem(name)
            found[name] = next((c for c in stems if _stem(c) == stem), stems[0])
        else:
            missing.append(name)
    return {"found": found, "missing": missing}
