"""A safe file name for an export.

``safe_filename`` turns a proposed export name into one file name that
macOS, Windows and Linux all accept: the characters the three systems
refuse (``/ \\ : * ? " < > |``) and the control characters below code 32
become ``-``, runs of whitespace become one space, leading and trailing
spaces and dots are stripped (Windows cannot have them), an empty result
becomes ``untitled``, a Windows-reserved base name gets a ``_`` prefix,
and the name is at most ``max_len`` characters, its last extension kept
when the base is cut instead. Finnish letters and emoji pass through
untouched: nothing is normalised away.

The reserved prefix and the length cut interact, so the order is fit,
prefix, fit again: a cut can turn a base into a reserved word
(``"control.webm"`` at ``max_len`` 8 fits to ``"con.webm"``) and the
prefix can push a fitted name over ``max_len``. After one ``_`` the base
starts with ``_`` and can never be reserved again, so the order always
settles in one round. A cut never leaves a trailing space or dot either,
and the sanitiser strips as its last step, so a safe name is safe again
unchanged: the function is idempotent.

Pure Python, stdlib only, no kuulas imports, no I/O. Errors are plain
``ValueError`` with no user-facing text. No input is ever touched.
"""

from __future__ import annotations

import re

#: The characters none of the three file systems accepts in a name.
_BAD = set('/\\:*?"<>|')

#: Windows reserved base names: the part before the first dot, whatever
#: the extension ("CON.wav" cannot be created). Checked case-folded.
_RESERVED = ({"con", "prn", "aux", "nul"}
             | {f"com{i}" for i in range(1, 10)}
             | {f"lpt{i}" for i in range(1, 10)})

#: The fallback word: an export needs some name even when nothing is left
#: of the proposed one (the task's own fixed literal, not a translated
#: string, like chapter_list's "0:00 Intro").
_FALLBACK = "untitled"

#: The floor for max_len: a limit must leave room for a base of at least
#: two characters in front of the longest extension the rule keeps
#: ("." plus 5), so 8 is the smallest useful limit.
_MIN_MAX_LEN = 8

_WHITESPACE = re.compile(r"\s+")


def _sanitise(name: str) -> str:
    """``name`` with its unusable characters replaced and ends cleaned.

    The refused characters and the controls below code 32 become ``-``
    (one for one, so the name keeps its length); the whitespace collapse
    runs after that, so a tab, being code 9, becomes ``-`` and not a
    space; runs of the remaining whitespace become one space; leading
    and trailing spaces and dots are stripped; an empty result becomes
    the fallback word.
    """
    replaced = "".join(
        "-" if ord(char) < 32 or char in _BAD else char for char in name)
    stem = _WHITESPACE.sub(" ", replaced).strip(" .")
    return stem or _FALLBACK


def _last_extension(name: str) -> str:
    """The name's last extension, or ``""`` when there is none.

    An extension is a dot followed by 1-5 ASCII letters or digits at the
    very end of the name, the way the three systems know extensions.
    Only the last dot can hold one: the tail of any earlier dot contains
    that later dot, which is neither letter nor digit.
    """
    _head, dot, tail = name.rpartition(".")
    if dot and 1 <= len(tail) <= 5 and tail.isascii() and tail.isalnum():
        return dot + tail
    return ""


def _fit(name: str, max_len: int) -> str:
    """``name`` cut to at most ``max_len`` characters, if it must be.

    When a cut is needed the last extension, if any, is kept and the
    base in front of it is cut instead; without an extension the name
    is cut from the end. A cut can land right after a space or a dot,
    which the sanitiser's strip would remove on a second pass, so the
    cut end is stripped of spaces and dots.
    """
    if len(name) <= max_len:
        return name
    extension = _last_extension(name)
    if extension:
        base = name[: len(name) - len(extension)][: max_len - len(extension)]
        return base.rstrip(" .") + extension
    return name[:max_len].rstrip(" .")


def _reserved(name: str) -> bool:
    """True when Windows refuses the name whatever its extension: its
    base, the part before the first dot, is one of the reserved words,
    in any case."""
    return name.partition(".")[0].casefold() in _RESERVED


def safe_filename(name: str, max_len: int = 120) -> str:
    """A file name safe on macOS, Windows and Linux, from ``name``.

    The characters ``/ \\ : * ? " < > |`` and the control characters
    below code 32 become ``-``; runs of whitespace become one space;
    leading and trailing spaces and dots are stripped; an empty result
    becomes ``"untitled"``; a Windows-reserved base name (the part
    before the first dot, in any case, with or without an extension)
    gets a ``_`` prefix; and the whole name is at most ``max_len``
    characters, its last extension (a dot followed by 1-5 ASCII letters
    or digits) kept when the base is cut instead. Finnish letters and
    emoji stay: nothing is normalised away. The result is safe again
    unchanged: ``safe_filename`` is idempotent.

    Raises ``ValueError`` when ``name`` is not a string or ``max_len``
    is below 8. The input is never mutated.
    """
    if not isinstance(name, str):
        msg = f"name must be a string, got {type(name).__name__}"
        raise ValueError(msg)  # noqa: TRY004 - the spec pins ValueError, not TypeError
    if max_len < _MIN_MAX_LEN:
        msg = f"max_len must be at least {_MIN_MAX_LEN}, got {max_len}"
        raise ValueError(msg)
    result = _fit(_sanitise(name), max_len)
    if _reserved(result):
        # The prefix can push the name over max_len, and a cut can turn
        # a base into a reserved word, so fit again after prefixing; the
        # new base starts with "_" and cannot be reserved a second time.
        result = _fit("_" + result, max_len)
    return result
