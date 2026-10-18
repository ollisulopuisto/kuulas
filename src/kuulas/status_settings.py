"""Editing the status list itself (WP51), logic only.

The statuses an edit of a project moves through are the user's own
workflow, so the list is the user's to edit: labels renamed, added,
removed and reordered, statuses marked done or not, and a project's label
the user has since deleted put back so the project still shows it. This
module is that editing as pure functions over a status list — a tuple of
``(label, done)`` pairs; the model's ``Status`` objects, persistence and
the UI wiring convert and come later.

Every label this module stores is normalised — stripped, its whitespace
collapsed — and an empty label raises ``ValueError``. Lookups match
case-insensitively as given, the way ``status.is_done`` matches. All
functions return new tuples and never touch their inputs.
"""

from __future__ import annotations

#: One status: its label, and whether it represents a finished state.
StatusPair = tuple[str, bool]
#: The whole status list, in the order the workflow moves through it.
StatusList = tuple[StatusPair, ...]


def _normalise(text: str) -> str | None:
    """Strip and collapse whitespace; ``None`` when nothing is left."""
    result = " ".join(text.split())
    return result if result else None


def _find(statuses: StatusList, label: str) -> int:
    """The index of the pair whose label matches ``label``
    case-insensitively.

    Raises ``ValueError`` when no stored label matches.
    """
    key = label.casefold()
    for index, (stored, _done) in enumerate(statuses):
        if stored.casefold() == key:
            return index
    msg = f"unknown status label: {label!r}"
    raise ValueError(msg)


def rename(statuses: StatusList, old: str, new: str) -> StatusList:
    """The list with the matching status's label replaced by ``new``,
    its position and done flag kept.

    ``old`` matches case-insensitively as given; ``new`` is normalised
    (stripped, whitespace collapsed). An empty ``new``, an unknown ``old``
    or a ``new`` that equals another existing label case-insensitively
    raises ``ValueError``. Renaming only the case of the same label is
    allowed: the new label then equals the pair being renamed, not
    another one.
    """
    normalised = _normalise(new)
    if normalised is None:
        msg = "status label cannot be empty"
        raise ValueError(msg)
    index = _find(statuses, old)
    key = normalised.casefold()
    for i, (stored, _done) in enumerate(statuses):
        if i != index and stored.casefold() == key:
            msg = f"duplicate status label: {normalised!r}"
            raise ValueError(msg)
    return tuple(
        (normalised, done) if i == index else (stored, done)
        for i, (stored, done) in enumerate(statuses)
    )


def add(statuses: StatusList, label: str, done: bool = False) -> StatusList:
    """The list with a new status appended at the end.

    ``label`` is normalised; an empty label, or one that duplicates an
    existing label case-insensitively, raises ``ValueError``.
    """
    normalised = _normalise(label)
    if normalised is None:
        msg = "status label cannot be empty"
        raise ValueError(msg)
    key = normalised.casefold()
    for stored, _done in statuses:
        if stored.casefold() == key:
            msg = f"duplicate status label: {normalised!r}"
            raise ValueError(msg)
    return (*statuses, (normalised, done))


def remove(statuses: StatusList, label: str) -> StatusList:
    """The list without the status whose label matches ``label``
    case-insensitively.

    An unknown label raises ``ValueError``, and so does removing the last
    remaining status: the list may never become empty, or no edit could
    carry a status at all.
    """
    index = _find(statuses, label)
    if len(statuses) == 1:
        msg = "cannot remove the last status label"
        raise ValueError(msg)
    return tuple(pair for i, pair in enumerate(statuses) if i != index)


def move(statuses: StatusList, label: str, new_index: int) -> StatusList:
    """The list with the matching status placed at ``new_index``, done
    flag and label kept.

    ``new_index`` is clamped to the valid range — a negative index becomes
    0, an index past the end becomes the last slot — and an unknown label
    raises ``ValueError``.
    """
    index = _find(statuses, label)
    target = max(0, min(new_index, len(statuses) - 1))
    moved = statuses[index]
    remaining = [pair for i, pair in enumerate(statuses) if i != index]
    remaining.insert(target, moved)
    return tuple(remaining)


def set_done(statuses: StatusList, label: str, done: bool) -> StatusList:
    """The list with the matching status's ``done`` flag set to ``done``.

    The stored label keeps its own case and its position; an unknown label
    raises ``ValueError``.
    """
    index = _find(statuses, label)
    return tuple(
        (stored, done) if i == index else (stored, old_done)
        for i, (stored, old_done) in enumerate(statuses)
    )


def labels(statuses: StatusList) -> tuple[str, ...]:
    """The labels, in list order."""
    return tuple(label for label, _done in statuses)


def ensure_current(statuses: StatusList, label: str) -> StatusList:
    """A list that contains ``label``, so a project whose current status
    the user has since deleted still shows it.

    ``label`` is normalised and matched case-insensitively; when no stored
    label matches, it is appended at the end as not done. The check and a
    possible append use the same normalised label, so no duplicate can be
    created. An empty label raises ``ValueError``, exactly as ``add``
    does. The result is a new tuple even when the list already contains
    the label.
    """
    normalised = _normalise(label)
    if normalised is None:
        msg = "status label cannot be empty"
        raise ValueError(msg)
    key = normalised.casefold()
    if any(stored.casefold() == key for stored, _done in statuses):
        return (*statuses,)
    return (*statuses, (normalised, False))
