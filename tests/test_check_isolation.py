from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path so scripts can be imported as modules
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_isolation import (  # noqa: E402
    FileResult,
    format_table,
    parse_summary,
)


def test_parse_summary_passing():
    output = """
.......................                                                  [100%]
23 passed in 1.47s
"""
    s = parse_summary(output)
    assert s.passed == 23
    assert s.failed == 0
    assert s.errors == 0
    assert s.duration_s == 1.47
    assert s.ok is True


def test_parse_summary_with_failures():
    output = """
FAILED tests/test_messages.py::test_no_literal_user_messages_in_python - AssertionError
1 failed, 22 passed in 4.62s
"""
    s = parse_summary(output)
    assert s.passed == 22
    assert s.failed == 1
    assert s.errors == 0
    assert s.duration_s == 4.62
    assert s.ok is False


def test_parse_summary_with_errors():
    output = """
ERROR tests/test_spot.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.12s
"""
    s = parse_summary(output)
    assert s.passed == 0
    assert s.failed == 0
    assert s.errors == 1
    assert s.duration_s == 0.12
    assert s.ok is False


def test_parse_summary_with_warnings_and_deselected():
    output = """
=============================== warnings summary ===============================
1 passed, 47 deselected, 1 warning in 4.21s
"""
    s = parse_summary(output)
    assert s.passed == 1
    assert s.failed == 0
    assert s.errors == 0
    assert s.duration_s == 4.21
    assert s.ok is True


def test_parse_summary_with_skipped():
    output = """
================== 5 passed, 2 skipped, 1 failed in 2.50s ==================
"""
    s = parse_summary(output)
    assert s.passed == 5
    assert s.skipped == 2
    assert s.failed == 1
    assert s.duration_s == 2.50
    assert s.ok is False


def test_parse_summary_malformed_or_empty():
    s = parse_summary("")
    assert s.ok is False
    assert s.errors >= 1

    s2 = parse_summary("Segmentation fault (core dumped)")
    assert s2.ok is False
    assert s2.errors >= 1


def test_format_table():
    results = [
        FileResult(path="tests/test_a.py", ok=True, duration_s=0.25, output="ok"),
        FileResult(path="tests/test_b.py", ok=False, duration_s=1.50, output="failed"),
    ]
    table = format_table(results)
    assert "tests/test_a.py" in table
    assert "PASS" in table
    assert "0.25s" in table
    assert "tests/test_b.py" in table
    assert "FAIL" in table
    assert "1.50s" in table
