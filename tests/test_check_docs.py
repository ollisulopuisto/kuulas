"""Tests for scripts/check_docs.py."""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts directory to sys.path so check_docs can be imported as a module
scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

import check_docs  # noqa: E402


def test_newest_changelog_version():
    text = (
        "# Changelog\n\n"
        "## [v26.10.18.11] - 2026-10-18\n\n"
        "- Recent change\n\n"
        "## [v26.10.18.10] - 2026-10-18\n\n"
        "- Older change\n"
    )
    assert check_docs.newest_changelog_version(text) == "v26.10.18.11"


def test_newest_changelog_version_missing():
    assert check_docs.newest_changelog_version("# No headings here") is None


def test_project_version():
    text = (
        '[project]\n'
        'name = "kuulas"\n'
        'version = "26.10.18.11"\n'
        'description = "DAW"\n'
    )
    assert check_docs.project_version(text) == "26.10.18.11"

    single_quotes = "version = '1.0.0.1'\n"
    assert check_docs.project_version(single_quotes) == "1.0.0.1"


def test_project_version_missing():
    assert check_docs.project_version('[project]\nname = "kuulas"') is None


def test_duplicate_headings_clean():
    text = (
        "# Title\n\n"
        "## Triage\n\n"
        "### WP0 — Baseline\n\n"
        "### WP1 — Session\n\n"
        "### WP2 — Playback\n"
    )
    assert check_docs.duplicate_headings(text) == []


def test_duplicate_headings_exact():
    text = (
        "### WP1 — Session\n"
        "### WP2 — Playback\n"
        "### WP1 — Session\n"
    )
    assert check_docs.duplicate_headings(text) == ["### WP1 — Session"]


def test_duplicate_headings_same_wp():
    text = (
        "### WP10 — Voice chain\n"
        "### WP11 — Export\n"
        "### WP10 — Duplicated voice chain\n"
    )
    assert check_docs.duplicate_headings(text) == ["### WP10 — Duplicated voice chain"]


def test_duplicate_headings_ignores_non_wp():
    text = (
        "## Triage\n"
        "## Triage\n"
        "### Other section\n"
        "### Other section\n"
    )
    assert check_docs.duplicate_headings(text) == []


def test_missing_rows_all_present():
    plan = "### WP1 — Session\n### WP2 — Playback\n"
    roadmap = "| R1 | WP1 |\n| R2 | WP2 |\n"
    assert check_docs.missing_rows(roadmap, plan) == []


def test_missing_rows_detects_missing():
    plan = "### WP1 — Session\n### WP2 — Playback\n### WP3 — HTTP API\n"
    roadmap = "| R1 | WP1 |\n| R2 | WP2 |\n"
    assert check_docs.missing_rows(roadmap, plan) == ["WP3"]


def test_missing_rows_respects_word_boundary():
    # WP1 is in plan, but roadmap only has WP10, not WP1
    plan = "### WP1 — Session\n"
    roadmap = "| R10 | WP10 |\n"
    assert check_docs.missing_rows(roadmap, plan) == ["WP1"]


def test_main_clean(tmp_path, capsys):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [v26.10.18.1] - 2026-10-18\n")
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('version = "26.10.18.1"\n')
    plan = tmp_path / "PLAN.md"
    plan.write_text("### WP1 — Test\n")
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("WP1 is documented\n")

    code = check_docs.main([
        "--changelog", str(cl),
        "--pyproject", str(pyproj),
        "--plan", str(plan),
        "--roadmap", str(roadmap),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Version OK" in out


def test_main_version_mismatch(tmp_path, capsys):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [v26.10.18.2] - 2026-10-18\n")
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('version = "26.10.18.1"\n')
    plan = tmp_path / "PLAN.md"
    plan.write_text("### WP1 — Test\n")
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("WP1 is documented\n")

    code = check_docs.main([
        "--changelog", str(cl),
        "--pyproject", str(pyproj),
        "--plan", str(plan),
        "--roadmap", str(roadmap),
    ])
    assert code == 1
    out = capsys.readouterr().out
    assert "mismatch" in out.lower()


def test_main_duplicate_heading(tmp_path, capsys):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [v26.10.18.1] - 2026-10-18\n")
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('version = "26.10.18.1"\n')
    plan = tmp_path / "PLAN.md"
    plan.write_text("### WP1 — Test\n### WP1 — Test\n")
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("WP1 is documented\n")

    code = check_docs.main([
        "--changelog", str(cl),
        "--pyproject", str(pyproj),
        "--plan", str(plan),
        "--roadmap", str(roadmap),
    ])
    assert code == 1
    out = capsys.readouterr().out
    assert "Duplicate headings" in out


def test_main_missing_rows_warns_only(tmp_path, capsys):
    cl = tmp_path / "CHANGELOG.md"
    cl.write_text("## [v26.10.18.1] - 2026-10-18\n")
    pyproj = tmp_path / "pyproject.toml"
    pyproj.write_text('version = "26.10.18.1"\n')
    plan = tmp_path / "PLAN.md"
    plan.write_text("### WP1 — Test\n### WP99 — Missing\n")
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text("WP1 is documented\n")

    code = check_docs.main([
        "--changelog", str(cl),
        "--pyproject", str(pyproj),
        "--plan", str(plan),
        "--roadmap", str(roadmap),
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Warning" in out
    assert "WP99" in out
