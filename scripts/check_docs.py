#!/usr/bin/env python3
"""Check documentation agreement with code and roadmap (T28).

Verifies:
1. Version agreement: pyproject.toml version equals CHANGELOG.md newest version.
2. No duplicate headings: no duplicate level-3 work package headings (### WPnn)
   in docs/PLAN.md.
3. Roadmap coverage: warns if any work package defined in docs/PLAN.md is missing
   from ROADMAP.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def newest_changelog_version(text: str) -> str | None:
    """Return the version of the first heading ## [vYY.MM.DD.N] in CHANGELOG.md."""
    m = re.search(r"^##\s+\[(v\d+\.\d+\.\d+(?:\.\d+)?)\]", text, re.MULTILINE)
    return m.group(1) if m else None


def project_version(text: str) -> str | None:
    """Return version = "..." from pyproject.toml."""
    m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return m.group(1) if m else None


def duplicate_headings(text: str) -> list[str]:
    """Return headings that appear more than once in docs/PLAN.md (### WPnn ones)."""
    seen_lines: set[str] = set()
    seen_wps: dict[str, str] = {}
    duplicates: list[str] = []

    for line in text.splitlines():
        line_clean = line.strip()
        m = re.match(r"^###\s+(WP\d+[a-z]?)", line_clean)
        if not m:
            continue
        wp_id = m.group(1)
        if line_clean in seen_lines or wp_id in seen_wps:
            if line_clean not in duplicates:
                duplicates.append(line_clean)
        else:
            seen_lines.add(line_clean)
            seen_wps[wp_id] = line_clean

    return duplicates


def missing_rows(roadmap_text: str, plan_text: str) -> list[str]:
    """Return work package ids in PLAN.md (### WP...) not mentioned in ROADMAP.md."""
    plan_wps: list[str] = []
    for line in plan_text.splitlines():
        m = re.match(r"^###\s+(WP\d+[a-z]?)", line.strip())
        if m:
            wp = m.group(1)
            if wp not in plan_wps:
                plan_wps.append(wp)

    return [wp for wp in plan_wps if not re.search(rf"\b{re.escape(wp)}\b", roadmap_text)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--changelog",
        type=Path,
        default=REPO_ROOT / "CHANGELOG.md",
        help="Path to CHANGELOG.md",
    )
    ap.add_argument(
        "--pyproject",
        type=Path,
        default=REPO_ROOT / "pyproject.toml",
        help="Path to pyproject.toml",
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=REPO_ROOT / "docs" / "PLAN.md",
        help="Path to docs/PLAN.md",
    )
    ap.add_argument(
        "--roadmap",
        type=Path,
        default=REPO_ROOT / "ROADMAP.md",
        help="Path to ROADMAP.md",
    )
    args = ap.parse_args(argv)

    for path, label in [
        (args.changelog, "CHANGELOG"),
        (args.pyproject, "pyproject.toml"),
        (args.plan, "docs/PLAN.md"),
        (args.roadmap, "ROADMAP.md"),
    ]:
        if not path.is_file():
            sys.stderr.write(f"File not found: {label} ({path})\n")
            return 1

    try:
        changelog_text = args.changelog.read_text(encoding="utf-8")
        pyproject_text = args.pyproject.read_text(encoding="utf-8")
        plan_text = args.plan.read_text(encoding="utf-8")
        roadmap_text = args.roadmap.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"Error reading documentation files: {exc}\n")
        return 1

    has_error = False

    # 1. Version check
    cl_ver = newest_changelog_version(changelog_text)
    proj_ver = project_version(pyproject_text)

    if not cl_ver:
        print(
            "Error: No version heading found in CHANGELOG.md "
            "(expected ## [vYY.MM.DD.N])"
        )
        has_error = True
    if not proj_ver:
        print("Error: No version found in pyproject.toml")
        has_error = True
    if cl_ver and proj_ver:
        cleaned_cl_ver = cl_ver.lstrip("v")
        if cleaned_cl_ver != proj_ver:
            print(
                f"Version mismatch: CHANGELOG.md has {cl_ver} ({cleaned_cl_ver}), "
                f"pyproject.toml has {proj_ver}"
            )
            has_error = True
        else:
            print(f"Version OK: {proj_ver}")

    # 2. Duplicate headings check
    dups = duplicate_headings(plan_text)
    if dups:
        print(f"Duplicate headings in PLAN.md ({len(dups)}):")
        for d in dups:
            print(f"  {d}")
        has_error = True
    else:
        print("Headings OK: no duplicate WP headings in PLAN.md")

    # 3. Missing rows in ROADMAP.md (warning only)
    missing = missing_rows(roadmap_text, plan_text)
    if missing:
        print(
            f"Warning: {len(missing)} work package(s) in PLAN.md "
            "not mentioned in ROADMAP.md:"
        )
        for wp in missing:
            print(f"  {wp}")
    else:
        print("Roadmap OK: all work packages mentioned")

    if has_error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
