"""Status tracking model (WP51), logic only.

Pure functions for managing a publication workflow history. Time values are
passed in by the caller as UTC ISO-8601 strings; this module never reads the
clock.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Status:
    """A workflow status and whether it represents a finished state."""

    label: str
    done: bool


DEFAULT_STATUSES: tuple[Status, ...] = (
    Status("Draft", False),
    Status("Ready for review", False),
    Status("In review", False),
    Status("Needs fixes", False),
    Status("Reviewed", False),
    Status("Approved", True),
    Status("Published", True),
)


@dataclass(frozen=True)
class HistoryEntry:
    """One change in the status history of a piece of content."""

    label: str
    who: str
    at: str
    note: str = ""


def normalise_label(text: str) -> str | None:
    """Strip and collapse whitespace; return ``None`` for an empty result."""
    result = " ".join(text.split())
    return result if result else None


def set_status(
    history: tuple[HistoryEntry, ...],
    label: str,
    who: str,
    now: str,
    note: str = "",
) -> tuple[HistoryEntry, ...]:
    """Append a new history entry, or return ``history`` unchanged if the
    status is already the current one (case-insensitive).

    Raises ``ValueError`` when ``label`` is empty after normalisation.
    """
    normalised = normalise_label(label)
    if normalised is None:
        msg = "status label cannot be empty"
        raise ValueError(msg)
    if history and history[-1].label.casefold() == normalised.casefold():
        return history
    return (*history, HistoryEntry(normalised, who, now, note))


def current(history: tuple[HistoryEntry, ...]) -> str | None:
    """The current status label, or ``None`` for an empty history."""
    return history[-1].label if history else None


def is_done(label: str, statuses: tuple[Status, ...]) -> bool:
    """Whether ``label`` is a finished status. Unknown labels are not done."""
    for status in statuses:
        if status.label.casefold() == label.casefold():
            return status.done
    return False


def to_dicts(history: tuple[HistoryEntry, ...]) -> list[dict[str, object]]:
    """Serialise a history tuple to plain dictionaries."""
    return [asdict(entry) for entry in history]


def from_dicts(items: list[dict[str, object]]) -> tuple[HistoryEntry, ...]:
    """Deserialise a history from plain dictionaries.

    Unknown keys are ignored, ``note`` defaults to ``""``, and items without a
    ``label`` are dropped.
    """
    entries: list[HistoryEntry] = []
    for item in items:
        label = item.get("label")
        if not isinstance(label, str) or normalise_label(label) is None:
            continue
        who = item.get("who", "")
        at = item.get("at", "")
        note = item.get("note", "")
        entries.append(
            HistoryEntry(
                label=label,
                who=who if isinstance(who, str) else "",
                at=at if isinstance(at, str) else "",
                note=note if isinstance(note, str) else "",
            ),
        )
    return tuple(entries)
