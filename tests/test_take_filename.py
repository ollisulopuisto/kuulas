"""Tests for take file name formatting (T62)."""

from datetime import UTC, datetime

import pytest

from kuulas.take_filename import take_filename


def test_spec_example():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    assert (
        take_filename(when, "vst s13e04", "Olli", "Take 1")
        == "2026-10-15 14-32-07 vst s13e04 - Olli - Take 1"
    )
    # Also test naive datetime as specified
    when_naive = datetime(2026, 10, 15, 14, 32, 7)  # noqa: DTZ001 - spec pins naive datetime
    assert (
        take_filename(when_naive, "vst s13e04", "Olli", "Take 1")
        == "2026-10-15 14-32-07 vst s13e04 - Olli - Take 1"
    )


def test_empty_track():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    assert (
        take_filename(when, "vst s13e04", "", "Take 1")
        == "2026-10-15 14-32-07 vst s13e04 - Take 1"
    )
    # Whitespace only also treated as empty
    assert (
        take_filename(when, "vst s13e04", "   ", "Take 1")
        == "2026-10-15 14-32-07 vst s13e04 - Take 1"
    )


def test_empty_project():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    assert (
        take_filename(when, "", "Olli", "Take 1")
        == "2026-10-15 14-32-07 Olli - Take 1"
    )
    assert (
        take_filename(when, "   ", "Olli", "Take 1")
        == "2026-10-15 14-32-07 Olli - Take 1"
    )


def test_empty_take():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    assert (
        take_filename(when, "vst s13e04", "Olli", "")
        == "2026-10-15 14-32-07 vst s13e04 - Olli"
    )
    assert (
        take_filename(when, "vst s13e04", "Olli", "   ")
        == "2026-10-15 14-32-07 vst s13e04 - Olli"
    )


def test_all_text_empty():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    assert take_filename(when, "", "", "") == "2026-10-15 14-32-07"
    assert take_filename(when, "   ", "   ", "   ") == "2026-10-15 14-32-07"


def test_forbidden_characters():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    res = take_filename(when, 'vst: "s13/e04"?', "Host *|? <1>", "Take #1>")
    for bad in '/\\:*?"<>|':
        assert bad not in res


def test_very_long_project():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    long_project = "A" * 200
    res = take_filename(when, long_project, "Olli", "Take 1")
    assert len(res) <= 120
    assert res.startswith("2026-10-15 14-32-07 ")
    assert res.endswith(" - Olli - Take 1")


def test_midnight_and_single_digit_zero_padded():
    when = datetime(2026, 1, 2, 0, 5, 9, tzinfo=UTC)
    res = take_filename(when, "proj", "track", "Take 1")
    assert res == "2026-01-02 00-05-09 proj - track - Take 1"


def test_type_errors():
    when = datetime(2026, 10, 15, 14, 32, 7, tzinfo=UTC)
    with pytest.raises(ValueError, match="when must be a datetime"):
        take_filename("2026-10-15", "proj", "track", "take")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="project must be a string"):
        take_filename(when, 123, "track", "take")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="track must be a string"):
        take_filename(when, "proj", None, "take")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="take must be a string"):
        take_filename(when, "proj", "track", ["take"])  # type: ignore[arg-type]
