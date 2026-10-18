"""gain_scale.py and clip_overs.py agree with the JS ports.

ui/gain-scale.js and ui/clip-overs.js read the same cases from
ui/tests/fixtures/gain-overs-cases.json. Strings "-inf" stand for -infinity.
"""

import json
from pathlib import Path

import pytest

from kuulas.clip_overs import max_over_db, overs
from kuulas.gain_scale import envelope_db_at, total_gain_db, waveform_scale

FIXTURES = Path(__file__).parent.parent / "ui" / "tests" / "fixtures"
FIXTURE = FIXTURES / "gain-overs-cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))


def num(value):
    return float(value) if isinstance(value, str) else value


@pytest.mark.parametrize("case", CASES["total"])
def test_total(case):
    got = total_gain_db(*[num(a) for a in case["args"]])
    assert got == pytest.approx(num(case["result"]))


@pytest.mark.parametrize("case", CASES["scale"])
def test_scale(case):
    args = {"max_scale": case["max"]} if "max" in case else {}
    assert waveform_scale(num(case["db"]), **args) == pytest.approx(case["result"])


@pytest.mark.parametrize("case", CASES["envelope"])
def test_envelope(case):
    points = [tuple(p) for p in case["points"]]
    assert envelope_db_at(points, case["frame"]) == pytest.approx(case["result"])


@pytest.mark.parametrize("case", CASES["overs"])
def test_overs(case):
    peaks = [tuple(p) for p in case["peaks"]]
    args = {"limit_db": case["limit"]} if "limit" in case else {}
    assert overs(peaks, case["gain"], **args) == [tuple(r) for r in case["result"]]


@pytest.mark.parametrize("case", CASES["max_over"])
def test_max_over(case):
    peaks = [tuple(p) for p in case["peaks"]]
    assert max_over_db(peaks, case["gain"]) == pytest.approx(case["result"], abs=1e-3)
