"""What's New: shipped changelog entries, never [Unreleased], never an error."""

import pytest

from kuulas import build_info, whatsnew

SAMPLE = """# Changelog

## [Unreleased]

- **Unshipped.** Must never show.

## [v26.10.30.6] - 2026-10-30

- **Newest shipped.** A note.

## [v26.10.30.4] - 2026-10-30

- **Older shipped.** Another note.

## [v26.10.29.1] - 2026-10-29

- **Oldest.** A third note.
"""


def test_parse_skips_unreleased_and_keeps_order():
    entries = whatsnew.parse_changelog(SAMPLE)
    assert [e["version"] for e in entries] == ["26.10.30.6", "26.10.30.4", "26.10.29.1"]
    assert entries[0]["date"] == "2026-10-30"
    assert "Newest shipped" in entries[0]["body"]


@pytest.fixture
def sample_file(tmp_path, monkeypatch):
    path = tmp_path / "CHANGELOG.md"
    path.write_text(SAMPLE, encoding="utf-8")
    monkeypatch.setattr(whatsnew, "changelog_path", lambda: path)
    return path


def test_upgrade_lists_everything_since_the_seen_version(sample_file):
    result = whatsnew.whats_new("26.10.29.1", "26.10.30.6")
    assert [e["version"] for e in result["entries"]] == ["26.10.30.6", "26.10.30.4"]
    assert result["available"]


def test_no_upgrade_is_empty(sample_file):
    assert whatsnew.whats_new("26.10.30.6", "26.10.30.6")["entries"] == []


def test_manual_open_shows_only_the_current_version(sample_file):
    entries = whatsnew.whats_new(None, "26.10.30.6")["entries"]
    assert [e["version"] for e in entries] == ["26.10.30.6"]


def test_entries_newer_than_the_running_build_never_show(sample_file):
    # A checkout behind its own changelog still tells the truth.
    entries = whatsnew.whats_new("26.10.29.1", "26.10.30.4")["entries"]
    assert [e["version"] for e in entries] == ["26.10.30.4"]


def test_missing_changelog_is_unavailable_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(whatsnew, "changelog_path", lambda: None)
    result = whatsnew.whats_new(None, "26.10.30.6")
    assert result == {"version": "26.10.30.6", "entries": [], "available": False}


def test_repo_changelog_matches_the_running_version():
    version = build_info.version()
    result = whatsnew.whats_new(None, version or "")
    if version:  # a checkout with a shipped changelog shows its own notes
        assert result["available"]
        assert [e["version"] for e in result["entries"]] == [version]
