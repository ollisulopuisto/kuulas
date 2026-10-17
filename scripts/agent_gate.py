#!/usr/bin/env python3
"""The gate an agent must pass before it reports ready-for-review.

Run from the agent's worktree:

    uv run python scripts/agent_gate.py --allow 'src/kuulas/foo.py' \
        --allow 'tests/test_foo.py' --allow 'src/kuulas/locales/*.json'

It checks what past reviews found by hand: files outside the task's list,
files nobody but the coordinator may touch, locale files out of step,
hard-coded readable text, decisions made by comparing a translated text,
whole-file media reads, a branch that is behind main, uncommitted work, tests
that fail alone, and a change that is too big. Paste the final PASS or FAIL
output into the ready-for-review entry. Exit status 0 is PASS.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

#: Only the coordinator edits these. Never allowed, whatever --allow says.
COORDINATOR_ONLY = (
    "CHANGELOG.md", "ROADMAP.md", "docs/PLAN.md", "docs/FORMAT.md", "uv.lock",
    "pyproject.toml", "AGENTS.md", "CLAUDE.md", "GEMINI.md", "docs/handoffs/*",
)

_LABEL = re.compile(r"""\bcommit\(\s*f?["']""")
_LABEL_VAR = re.compile(r"""\blabel\s*=\s*f?["'][A-Za-z]""")
_TEXT_COMPARE = re.compile(
    r"""\.(startswith|endswith)\(\s*f?["'][A-Za-z]|\b(label|title|message)\s*==\s*["'][A-Za-z]""")
_WHOLE_READ = re.compile(r"""\bsf\.read\(|\bsoundfile\.read\(|\blibrosa\.load\(""")


def out_of_scope(changed: list[str], allowed: list[str]) -> list[str]:
    """Changed files that are not allowed, or that only the coordinator may edit."""
    bad = []
    for path in changed:
        locked = any(fnmatch.fnmatch(path, pat) for pat in COORDINATOR_ONLY)
        if locked or not any(fnmatch.fnmatch(path, pat) for pat in allowed):
            bad.append(path)
    return bad


def locale_diff(en: dict, fi: dict) -> tuple[list[str], list[str]]:
    """(keys only in en, keys only in fi)."""
    return sorted(set(en) - set(fi)), sorted(set(fi) - set(en))


def hardcoded_labels(added: list[str]) -> list[str]:
    """Added lines that commit a step with a literal label instead of ``t(...)``."""
    hits = []
    for i, line in enumerate(added):
        nxt = added[i + 1].strip() if i + 1 < len(added) else ""
        split_call = line.rstrip().endswith("commit(") and nxt[:1] in ('"', "'", "f")
        if _LABEL.search(line) or _LABEL_VAR.search(line) or (
                split_call and re.match(r"""f?["']""", nxt)):
            hits.append(line)
    return hits


def compares_text(added: list[str]) -> list[str]:
    """Added lines that decide something by comparing readable (translated) text."""
    return [line for line in added if _TEXT_COMPARE.search(line)]


def whole_file_reads(added: list[str]) -> list[str]:
    """Added lines that read a whole media file into memory."""
    return [line for line in added if _WHOLE_READ.search(line)]


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (path.startswith(("tests/", "ui/tests/")) or name.startswith("test_")
            or name.endswith(".test.js"))


def size_without_tests(numstat: list[str]) -> tuple[int, int]:
    """(files, changed lines) of a ``git diff --numstat`` output, test files left
    out: the size rule is about the code a reviewer has to read. Binary rows
    (``-`` counts) are a file with no lines."""
    files = lines = 0
    for row in numstat:
        added, removed, path = row.split("\t", 2)
        if _is_test_path(path):
            continue
        files += 1
        lines += (int(added) if added.isdigit() else 0) + (
            int(removed) if removed.isdigit() else 0)
    return files, lines


def too_big(*, files: int, lines: int, max_files: int, max_lines: int) -> bool:
    return files > max_files or lines > max_lines


# -- running it ------------------------------------------------------------

def _run(*cmd: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)  # noqa: S603


def _added_lines(base: str) -> list[str]:
    diff = _run("git", "diff", "-U0", f"{base}...HEAD", "--", "src", "ui").stdout
    return [line[1:] for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow", action="append", default=[], help="file or glob")
    ap.add_argument("--base", default="main")
    ap.add_argument("--max-files", type=int, default=6)
    ap.add_argument("--max-lines", type=int, default=400)
    args = ap.parse_args()
    problems: list[str] = []

    if _run("git", "status", "--porcelain").stdout.strip():
        problems.append("uncommitted changes: commit or discard them")
    if _run("git", "merge-base", "--is-ancestor", args.base, "HEAD").returncode != 0:
        problems.append(f"branch is behind {args.base}: merge {args.base} into it")

    changed = _run("git", "diff", "--name-only", f"{args.base}...HEAD").stdout.split()
    stat = _run("git", "diff", "--shortstat", f"{args.base}...HEAD").stdout.strip()
    numstat = _run("git", "diff", "--numstat", f"{args.base}...HEAD").stdout.splitlines()
    n_files, lines = size_without_tests(numstat)
    if bad := out_of_scope(changed, args.allow):
        problems.append(f"files outside the task or coordinator-only: {', '.join(bad)}")
    if too_big(files=n_files, lines=lines, max_files=args.max_files,
               max_lines=args.max_lines):
        problems.append(f"too big: {n_files} files, {lines} lines, tests not counted "
                        f"(limit {args.max_files} / {args.max_lines}); ask first")

    loc = Path("src/kuulas/locales")
    if (loc / "en.json").exists():
        only_en, only_fi = locale_diff(json.loads((loc / "en.json").read_text()),
                                       json.loads((loc / "fi.json").read_text()))
        if only_en or only_fi:
            problems.append(f"locale keys differ: only en {only_en}, only fi {only_fi}")

    added = _added_lines(args.base)
    checks = (
        ("literal commit label (use t(...))", hardcoded_labels(added)),
        ("decision by comparing readable text", compares_text(added)),
        ("whole media file read (use 60 s chunks)", whole_file_reads(added)),
    )
    for name, hits in checks:
        problems += [f"{name}: {line.strip()}" for line in hits]

    new_tests = [p for p in changed if re.fullmatch(r"tests/test_[\w]+\.py", p)]
    for test in new_tests:
        if _run("uv", "run", "pytest", "-q", test).returncode != 0:
            problems.append(f"{test} fails when run alone")
    if _run("uv", "run", "ruff", "check", ".").returncode != 0:
        problems.append("ruff check . fails")
    if _run("uv", "run", "pytest", "-q").returncode != 0:
        problems.append("the full test suite fails")

    print(stat or "no changes against " + args.base)
    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print("PASS")
    print("Reminder, not checked by a script: list every function that now runs "
          "while holding the session lock, and say none of them is slow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
