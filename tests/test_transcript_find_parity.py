"""The editor's find (ui/transcript-find.js) must match transcript_find.find.

Both read ui/tests/fixtures/find-cases.json; the node test checks the other side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kuulas.transcript_find import find

CASES = json.loads(
    (Path(__file__).parent.parent / "ui" / "tests" / "fixtures" / "find-cases.json")
    .read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_python_find_agrees_with_the_shared_cases(case):
    assert find(case["words"], case["query"]) == tuple(tuple(m) for m in case["matches"])
