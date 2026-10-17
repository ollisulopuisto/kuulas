#!/usr/bin/env python3
"""Run each test file alone to check test isolation.

The default language follows the machine, so a test can pass or fail depending
on run order. Running every test file in isolation verifies that tests do not
depend on shared global state or prior imports.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import getpass
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Summary:
    """Parsed metrics from a pytest summary line."""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.errors == 0 and (
            self.passed > 0 or self.skipped > 0
        )


@dataclass(frozen=True)
class FileResult:
    """Outcome of running a single test file."""

    path: str
    ok: bool
    duration_s: float
    output: str


def parse_summary(output: str) -> Summary:
    """Extract passed, failed, errors, and duration from pytest output."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return Summary(errors=1)

    for line in reversed(lines):
        # Match standard pytest summary pattern ending with e.g. "in 1.47s"
        m = re.search(r"(?:=+\s*)?(.*?)\b(\d+(?:\.\d+)?)\s*s(?:\s*=+)?$", line)
        if not m:
            continue
        prefix, dur_str = m.group(1), m.group(2)
        has_keywords = (
            "passed" in prefix
            or "failed" in prefix
            or "error" in prefix
            or "skipped" in prefix
        )
        if not has_keywords:
            continue

        try:
            dur = float(dur_str)
        except ValueError:
            dur = 0.0

        p = re.search(r"(\d+)\s+passed", prefix)
        f = re.search(r"(\d+)\s+failed", prefix)
        e = re.search(r"(\d+)\s+error", prefix)
        s = re.search(r"(\d+)\s+skipped", prefix)

        passed = int(p.group(1)) if p else 0
        failed = int(f.group(1)) if f else 0
        errors = int(e.group(1)) if e else 0
        skipped = int(s.group(1)) if s else 0

        return Summary(
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_s=dur,
        )

    # If no valid summary line was recognized, the test run did not complete normally
    return Summary(errors=1)


def run_one(path: Path) -> FileResult:
    """Run pytest for a single test file and parse its outcome."""
    env = os.environ.copy()
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = "shared"
    worker_cache = (
        Path(tempfile.gettempdir())
        / f"kuulas-numba-{user}-{os.getpid()}-{path.stem}"
    )
    worker_cache.mkdir(parents=True, exist_ok=True)
    env["NUMBA_CACHE_DIR"] = str(worker_cache)

    cmd = ["uv", "run", "pytest", "-q", str(path)]
    proc = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    combined = (proc.stdout + "\n" + proc.stderr).strip()
    summary = parse_summary(combined)
    is_ok = proc.returncode == 0 and summary.ok
    return FileResult(
        path=str(path),
        ok=is_ok,
        duration_s=summary.duration_s,
        output=combined,
    )


def format_table(results: list[FileResult]) -> str:
    """Format test results into a tabular text display."""
    max_name = max((len(r.path) for r in results), default=30)
    col_w = max(max_name, 30)
    lines = [
        f"{'File':<{col_w}}  {'Result':<8}  {'Time':>8}",
        f"{'-' * col_w}  {'-' * 8}  {'-' * 8}",
    ]
    for r in results:
        res_str = "PASS" if r.ok else "FAIL"
        time_str = f"{r.duration_s:.2f}s"
        lines.append(f"{r.path:<{col_w}}  {res_str:<8}  {time_str:>8}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel test workers (default: 4)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Optional test files to run (defaults to tests/test_*.py)",
    )
    args = parser.parse_args()

    if args.files:
        test_files = [Path(f) for f in args.files]
    else:
        test_dir = Path("tests")
        test_files = sorted(test_dir.glob("test_*.py"))

    if not test_files:
        print("No test files found.")
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_path = {executor.submit(run_one, p): p for p in test_files}
        results = [
            future.result()
            for future in concurrent.futures.as_completed(future_to_path)
        ]

    # Sort results by file path for consistent table display
    results.sort(key=lambda r: r.path)

    print(format_table(results))

    failures = [r for r in results if not r.ok]
    if failures:
        print(f"\n{len(failures)} failing file(s):")
        print("-" * 50)
        for r in failures:
            print(f"\n{r.path}:")
            tail = "\n".join(r.output.strip().splitlines()[-20:])
            print(tail)
        return 1

    print(f"\nAll {len(results)} test file(s) passed in isolation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
