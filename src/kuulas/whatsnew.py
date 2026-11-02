"""What's New: the shipped changelog entries between two versions.

The source of truth is the repo's ``CHANGELOG.md`` (Keep a Changelog,
calendar versions ``vYY.MM.DD.N``); only shipped sections count, so
``[Unreleased]`` never shows. A missing changelog (a trimmed package)
means "nothing to tell", never an error - the dialog then stays away.
"""

from __future__ import annotations

import re
from pathlib import Path

_HEADING = re.compile(
    r"^## \[v?(\d+(?:\.\d+)+)\] - (\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE
)


def changelog_path() -> Path | None:
    """The shipped CHANGELOG.md, or None where it was not shipped.

    In a bundle it sits beside the package (staged like build_label.txt);
    in a checkout it is the repo root's."""
    package = Path(__file__).resolve().parent
    for path in (package / "CHANGELOG.md", package.parents[1] / "CHANGELOG.md"):
        if path.is_file():
            return path
    return None


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def parse_changelog(text: str) -> list[dict[str, str]]:
    """[{'version', 'date', 'body'}] newest first, without [Unreleased]."""
    headings = list(_HEADING.finditer(text))
    entries = []
    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        # A section ends at the next shipped heading or at [Unreleased]'s.
        unreleased = text.find("## [Unreleased]", match.end(), end)
        body_end = unreleased if unreleased != -1 else end
        body = text[match.end() : body_end].strip()
        if body:
            entries.append(
                {"version": match.group(1), "date": match.group(2), "body": body}
            )
    return entries


def whats_new(after: str | None, current: str) -> dict:
    """Entries newer than ``after`` (None: only the current version's).

    ``current`` is the running build's version; entries above it cannot be
    shipped yet and are left out, so a checkout ahead of its changelog
    still tells the truth."""
    path = changelog_path()
    if path is None or not current:
        return {"version": current, "entries": [], "available": False}
    try:
        entries = parse_changelog(path.read_text(encoding="utf-8"))
    except OSError:
        return {"version": current, "entries": [], "available": False}
    current_key = _key(current.lstrip("v"))
    if after is None:  # manual open: the current version's notes only
        entries = [e for e in entries if _key(e["version"]) == current_key]
    else:
        after_key = _key(after.lstrip("v"))
        entries = [e for e in entries if after_key < _key(e["version"]) <= current_key]
    return {"version": current, "entries": entries, "available": True}
