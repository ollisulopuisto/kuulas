"""Run only existing, root-level pytest modules listed by the CI path filter."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest


def parse_shard(spec: str) -> tuple[int, int]:
    """Parse a one-based shard number and its total, e.g. ``2/4``."""
    if not re.fullmatch(r"[1-9][0-9]*/[1-9][0-9]*", spec):
        raise ValueError(f"Expected a shard as N/M, got {spec!r}")
    number_text, total_text = spec.split("/")
    number, total = int(number_text), int(total_text)
    if number > total:
        raise ValueError(f"Shard {number} is outside 1..{total}")
    return number, total


def shard_items[Item](items: list[Item], spec: str) -> tuple[list[Item], list[Item]]:
    """Split one stable pytest collection into balanced, disjoint shard lists."""
    number, total = parse_shard(spec)
    selected, deselected = [], []
    for index, item in enumerate(items):
        (selected if index % total == number - 1 else deselected).append(item)
    return selected, deselected


def changed_test_modules(paths: list[str], repo_root: Path) -> list[str]:
    """Validate and sort changed module paths; deleted modules are not runnable."""
    root = repo_root.resolve()
    tests_dir = (root / "tests").resolve()
    selected: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path)
        candidate = (root / path).resolve()
        if (
            path.is_absolute()
            or candidate.parent != tests_dir
            or not candidate.name.startswith("test_")
            or candidate.suffix != ".py"
        ):
            raise ValueError(
                f"Expected a root-level tests/test_*.py path, got {raw_path!r}"
            )
        if candidate.is_file():
            selected.add(candidate.relative_to(root).as_posix())
    return sorted(selected)


def main() -> int:
    raw_paths = os.environ.get("KUULAS_CHANGED_PYTEST_FILES", "[]")
    paths = json.loads(raw_paths)
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError("KUULAS_CHANGED_PYTEST_FILES must be a JSON array of paths")
    modules = changed_test_modules(paths, Path(__file__).resolve().parents[1])
    if not modules:
        raise ValueError(
            "No changed test modules exist; route this change through the full suite"
        )
    return int(pytest.main(["-q", *modules, "--junitxml=test-results/pytest.xml"]))


if __name__ == "__main__":
    raise SystemExit(main())
