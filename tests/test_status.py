"""Tests for status tracking model."""

from __future__ import annotations

import pytest

from kuulas.status import (
    DEFAULT_STATUSES,
    HistoryEntry,
    Status,
    current,
    from_dicts,
    is_done,
    normalise_label,
    set_status,
    to_dicts,
)


class TestDefaultStatuses:
    def test_order_and_done_flags(self):
        labels = [status.label for status in DEFAULT_STATUSES]
        done_flags = [status.done for status in DEFAULT_STATUSES]
        assert labels == [
            "Draft",
            "Ready for review",
            "In review",
            "Needs fixes",
            "Reviewed",
            "Approved",
            "Published",
        ]
        assert done_flags == [False, False, False, False, False, True, True]

    def test_status_is_frozen(self):
        status = Status("Draft", False)
        with pytest.raises(AttributeError):
            status.label = "Other"  # type: ignore[misc]


class TestNormaliseLabel:
    def test_strips_and_collapses_inner_whitespace(self):
        assert normalise_label("  Ready   for   review  ") == "Ready for review"

    def test_returns_none_for_empty(self):
        assert normalise_label("") is None
        assert normalise_label("   ") is None

    def test_leaves_normal_label_unchanged(self):
        assert normalise_label("Draft") == "Draft"


class TestSetStatus:
    def test_appends_entry(self):
        history = ()
        result = set_status(history, "Draft", "kimi", "2026-10-18T10:00:00Z")
        assert result == (
            HistoryEntry(
                label="Draft",
                who="kimi",
                at="2026-10-18T10:00:00Z",
                note="",
            ),
        )

    def test_includes_note(self):
        history = ()
        result = set_status(history, "Draft", "kimi", "2026-10-18T10:00:00Z", "created")
        assert result[-1].note == "created"

    def test_no_op_when_same_label(self):
        history = set_status((), "Draft", "kimi", "2026-10-18T10:00:00Z")
        result = set_status(history, "Draft", "kimi", "2026-10-18T10:01:00Z")
        assert result == history

    def test_no_op_when_same_label_different_case(self):
        history = set_status((), "Draft", "kimi", "2026-10-18T10:00:00Z")
        result = set_status(history, "draft", "kimi", "2026-10-18T10:01:00Z")
        assert result == history

    def test_empty_label_raises_value_error(self):
        with pytest.raises(ValueError, match="label cannot be empty"):
            set_status((), "", "kimi", "2026-10-18T10:00:00Z")

    def test_empty_label_after_normalising_raises(self):
        with pytest.raises(ValueError, match="label cannot be empty"):
            set_status((), "   ", "kimi", "2026-10-18T10:00:00Z")


class TestCurrent:
    def test_empty_history_returns_none(self):
        assert current(()) is None

    def test_returns_last_label(self):
        history = (
            HistoryEntry(label="Draft", who="a", at="2026-10-18T10:00:00Z"),
            HistoryEntry(label="Ready for review", who="b", at="2026-10-18T10:01:00Z"),
        )
        assert current(history) == "Ready for review"


class TestIsDone:
    def test_known_done_status(self):
        assert is_done("Approved", DEFAULT_STATUSES) is True
        assert is_done("Published", DEFAULT_STATUSES) is True

    def test_known_undone_status(self):
        assert is_done("Draft", DEFAULT_STATUSES) is False

    def test_case_insensitive(self):
        assert is_done("approved", DEFAULT_STATUSES) is True
        assert is_done("DRAFT", DEFAULT_STATUSES) is False

    def test_unknown_label_is_not_done(self):
        assert is_done("Unknown", DEFAULT_STATUSES) is False


class TestDictRoundTrip:
    def test_to_dicts_and_from_dicts(self):
        history = (
            HistoryEntry(
                label="Draft",
                who="kimi",
                at="2026-10-18T10:00:00Z",
                note="initial",
            ),
        )
        items = to_dicts(history)
        assert items == [
            {
                "label": "Draft",
                "who": "kimi",
                "at": "2026-10-18T10:00:00Z",
                "note": "initial",
            },
        ]
        assert from_dicts(items) == history

    def test_unknown_extra_keys_ignored(self):
        items = [
            {
                "label": "Draft",
                "who": "kimi",
                "at": "2026-10-18T10:00:00Z",
                "extra": "ignored",
            },
        ]
        history = from_dicts(items)
        assert history == (
            HistoryEntry(label="Draft", who="kimi", at="2026-10-18T10:00:00Z"),
        )

    def test_missing_note_defaults_to_empty(self):
        items = [
            {
                "label": "Draft",
                "who": "kimi",
                "at": "2026-10-18T10:00:00Z",
            },
        ]
        history = from_dicts(items)
        assert history[0].note == ""

    def test_entries_without_label_dropped(self):
        items = [
            {"who": "kimi", "at": "2026-10-18T10:00:00Z"},
            {"label": "Draft", "who": "kimi", "at": "2026-10-18T10:01:00Z"},
        ]
        history = from_dicts(items)
        assert len(history) == 1
        assert history[0].label == "Draft"


class TestImmutability:
    def test_old_tuple_unchanged_by_set_status(self):
        history = ()
        set_status(history, "Draft", "kimi", "2026-10-18T10:00:00Z")
        assert history == ()

    def test_history_entry_is_frozen(self):
        entry = HistoryEntry(label="Draft", who="kimi", at="2026-10-18T10:00:00Z")
        with pytest.raises(AttributeError):
            entry.label = "Other"  # type: ignore[misc]
