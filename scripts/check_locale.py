#!/usr/bin/env python3
"""Check parity and references in locale files (WP33b).

Verifies:
1. Parity: every key in en.json exists in fi.json and vice versa.
2. References: every static key used in src/ or ui/ exists in en.json.
3. Unused: lists keys in en.json not statically referenced (informational warning).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Regex matching calls like t("a.b.c"), KuulasError("a.b.c", ...), EditError('a.b.c')
_KEY_REF = re.compile(
    r"""(?<![\w.$])(?:t|[A-Za-z0-9_]*Error)\s*\(\s*(["'])([a-zA-Z0-9_.-]+)\1\s*[,)]"""
)


def parity(en: Iterable[str], fi: Iterable[str]) -> tuple[list[str], list[str]]:
    """Return keys only in en and only in fi."""
    set_en = set(en)
    set_fi = set(fi)
    return sorted(set_en - set_fi), sorted(set_fi - set_en)


def referenced_keys(text: str) -> set[str]:
    """Extract every locale key referenced statically in the source text."""
    return {m.group(2) for m in _KEY_REF.finditer(text)}


def unused(keys: Iterable[str], referenced: Iterable[str]) -> list[str]:
    """Return keys defined but not referenced in the collected source."""
    return sorted(set(keys) - set(referenced))


def scan_sources(src_dir: Path, ui_dir: Path) -> set[str]:
    """Scan all python files in src_dir and javascript files in ui_dir."""
    referenced: set[str] = set()

    if src_dir.is_dir():
        for py_file in src_dir.rglob("*.py"):
            try:
                referenced.update(referenced_keys(py_file.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue

    if ui_dir.is_dir():
        for js_file in ui_dir.rglob("*.js"):
            # Exclude tests and node_modules in UI directory
            if any(part in ("tests", "node_modules") for part in js_file.parts):
                continue
            try:
                referenced.update(referenced_keys(js_file.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                continue

    return referenced


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check locale parity and references.")
    ap.add_argument(
        "--en",
        type=Path,
        default=REPO_ROOT / "src" / "kuulas" / "locales" / "en.json",
        help="Path to en.json",
    )
    ap.add_argument(
        "--fi",
        type=Path,
        default=REPO_ROOT / "src" / "kuulas" / "locales" / "fi.json",
        help="Path to fi.json",
    )
    ap.add_argument(
        "--src",
        type=Path,
        default=REPO_ROOT / "src",
        help="Source directory (Python files)",
    )
    ap.add_argument(
        "--ui",
        type=Path,
        default=REPO_ROOT / "ui",
        help="UI directory (JavaScript files)",
    )
    args = ap.parse_args(argv)

    if not args.en.is_file() or not args.fi.is_file():
        sys.stderr.write(f"Locale files not found: {args.en} or {args.fi}\n")
        return 1

    try:
        en_keys = set(json.loads(args.en.read_text(encoding="utf-8")))
        fi_keys = set(json.loads(args.fi.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Invalid JSON in locale file: {exc}\n")
        return 1

    has_error = False

    # 1. Parity check
    only_en, only_fi = parity(en_keys, fi_keys)
    if only_en or only_fi:
        has_error = True
        print("Parity mismatch:")
        if only_en:
            print(f"  only in en ({len(only_en)}): {', '.join(only_en)}")
        if only_fi:
            print(f"  only in fi ({len(only_fi)}): {', '.join(only_fi)}")

    # 2. Referenced keys check
    referenced = scan_sources(args.src, args.ui)
    missing = sorted(referenced - en_keys)
    if missing:
        has_error = True
        print(f"Missing referenced keys ({len(missing)}):")
        for key in missing:
            print(f"  {key}")

    # 3. Unused keys (warning list, informational)
    unref = unused(en_keys, referenced)
    if unref:
        print(f"Unused keys ({len(unref)} - informational warning):")
        for key in unref:
            print(f"  {key}")

    if has_error:
        return 1

    print(f"OK: {len(en_keys)} keys in sync, {len(referenced)} referenced keys valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
