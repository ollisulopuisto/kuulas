"""File names for exported stems.

``stem_names`` turns a list of track names into the file names the
tracks' stems export as: ``"<NN> <safe name>.<extension>"``, one per
track, in order. ``NN`` is the 1-based position, zero padded to the
width of the list length and at least two digits (three tracks give
``01``..``03``, 120 give ``001``..``120``); the name goes through
``safe_filename`` with ``max_len=100``; a track whose name is empty
after stripping uses ``Track``. ``extension`` is lower-cased and must
be 1-5 ASCII letters or digits without a dot.

The whole file names are unique ignoring case. The number prefixes are
distinct and fixed-width, so the wholes are unique by construction and
plain repeats never need help: two tracks both named ``Olli`` give
``01 Olli.wav`` and ``02 Olli.wav``. ``unique_name`` still runs on the
name part, against the whole names made so far, as the task's
safeguard: it fires only for a track literally named like an earlier
whole file name, and its `` 2`` lands before the extension, which
stays last.

Errors are plain ``ValueError`` with no user-facing text; ``Track`` is
the task's own fixed fallback word, not a translated string. No input
is ever touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from kuulas.safe_filename import safe_filename
from kuulas.unique_name import unique_name

#: The word for a track whose name is empty after stripping (the task's
#: own fixed literal, like safe_filename's "untitled").
_EMPTY_NAME = "Track"

#: The fewest digits a position number shows, whatever the list length.
_MIN_DIGITS = 2

#: How much of a track name may reach the file name.
_MAX_NAME = 100


def _width(count: int) -> int:
    """The digits a position number shows: the width of the list length
    as a decimal number, at least two."""
    return max(_MIN_DIGITS, len(str(count)))


def stem_names(track_names: Sequence[str], extension: str = "wav") -> list[str]:
    """The stem file names for ``track_names``, in order.

    Each name is ``"<NN> <safe name>.<extension>"``: ``NN`` the 1-based
    position zero padded to the width of the list length (at least two
    digits), the name through ``safe_filename`` with ``max_len=100``
    (``"Track"`` when empty after stripping), the extension lower-cased.
    The whole names are unique ignoring case: the number prefixes alone
    make them so, and ``unique_name`` guards the name part against the
    whole names made so far.

    Raises ``ValueError`` when ``extension`` is not a string or not 1-5
    ASCII letters or digits without a dot (checked before the list, so
    an empty list with a bad extension still raises), or when a track
    name is not a string. Returns ``[]`` for an empty list. The input is
    never mutated.
    """
    if not isinstance(extension, str):
        msg = f"extension must be a string, got {type(extension).__name__}"
        raise ValueError(msg)  # noqa: TRY004 - the contract is plain ValueError
    # A dot is neither letter nor digit, so isalnum alone refuses it.
    if not (1 <= len(extension) <= 5 and extension.isascii() and extension.isalnum()):
        msg = f"extension must be 1-5 ASCII letters or digits, got {extension!r}"
        raise ValueError(msg)
    suffix = "." + extension.lower()
    width = _width(len(track_names))
    names: list[str] = []
    for position, track_name in enumerate(track_names, start=1):
        if not isinstance(track_name, str):
            msg = f"track name must be a string, got {type(track_name).__name__}"
            raise ValueError(msg)  # noqa: TRY004 - the task pins ValueError
        if not track_name.strip():
            part = _EMPTY_NAME
        else:
            part = safe_filename(track_name, max_len=_MAX_NAME)
        # The safeguard: the part after the number against the whole
        # names made so far. The prefix already makes the wholes unique,
        # so this only fires for a part equal to an earlier whole.
        part = unique_name(part, names)
        names.append(f"{position:0{width}d} {part}{suffix}")
    return names
