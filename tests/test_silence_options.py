"""Auto-Silence options: validation, bit-identical defaults, the preview."""

import pytest
from gate_fixtures import RATE, conversation
from speechmix import grid, masks

from kuulas import analysis, ops, silence_options
from kuulas.silence_options import SilenceOptions


def test_the_defaults_are_todays_hard_coded_values():
    d = SilenceOptions()
    assert d.margin_db == grid.FLOOR_MARGIN_DB
    assert d.dominance_db == masks.DUCK_DOMINANCE_DB
    assert (d.min_open_s, d.min_closed_s) == (analysis.MIN_OPEN_S, analysis.MIN_CLOSED_S)
    assert (d.open_before_s, d.open_after_s) == (
        analysis.OPEN_BEFORE_S, analysis.OPEN_AFTER_S)


def test_parse_fills_defaults_and_ignores_unrelated_keys():
    assert silence_options.parse(None) == SilenceOptions()
    assert silence_options.parse({"track_ids": ["T0"]}) == SilenceOptions()
    assert silence_options.parse({"margin_db": 8}).margin_db == 8.0
    assert silence_options.parse({"margin_db": None}).margin_db == grid.FLOOR_MARGIN_DB


def test_parse_clamps_to_the_ranges():
    lo, hi = silence_options.RANGES["margin_db"]
    assert silence_options.parse({"margin_db": -50}).margin_db == lo
    assert silence_options.parse({"margin_db": 500}).margin_db == hi
    assert silence_options.parse({"min_open_s": -1}).min_open_s == 0.0


@pytest.mark.parametrize("bad", ["x", True, float("nan"), float("inf"), [1]])
def test_parse_refuses_what_is_not_a_number(bad):
    with pytest.raises(ops.EditError) as e:
        silence_options.parse({"margin_db": bad})
    assert e.value.key == "error.silence.bad_option"


def test_numeric_strings_are_accepted():
    assert silence_options.parse({"margin_db": "9.5"}).margin_db == 9.5


def test_as_dict_round_trips():
    o = SilenceOptions(margin_db=7.0, dominance_db=9.0)
    assert silence_options.parse(o.as_dict()) == o


def test_explicit_defaults_give_bit_identical_results():
    p, store = conversation(seconds=90)
    assert analysis.silence_ranges(p, store) == analysis.silence_ranges(
        p, store, SilenceOptions())
    assert analysis.auto_silence(p, store) == analysis.auto_silence(
        p, store, options=SilenceOptions())


def test_a_lower_margin_closes_less():
    p, store = conversation(seconds=90)
    base = analysis.preview_silence(p, store)
    gentle = analysis.preview_silence(p, store, SilenceOptions(margin_db=4.0))
    assert sum(r["close_s"] for r in gentle) < sum(r["close_s"] for r in base)


def test_the_dominance_changes_the_result():
    p, store = conversation(seconds=90, bleed=0.2)
    a = analysis.silence_ranges(p, store)
    b = analysis.silence_ranges(p, store, SilenceOptions(dominance_db=20.0))
    assert a != b


def test_longer_open_padding_closes_less():
    p, store = conversation(seconds=90)
    base = analysis.preview_silence(p, store)
    padded = analysis.preview_silence(
        p, store, SilenceOptions(open_before_s=0.5, open_after_s=1.0))
    assert sum(r["close_s"] for r in padded) < sum(r["close_s"] for r in base)


def test_preview_commits_nothing_and_reports_per_track():
    p, store = conversation(seconds=60)
    gated = ops.set_gate(p, "T0", [(0, 10 * RATE)])
    rows = analysis.preview_silence(gated, store)
    assert [r["track_id"] for r in rows] == ["T0", "T1", "T2", "T3"]
    t0 = rows[0]
    assert t0["now_s"] == 10.0
    assert rows[1]["now_s"] == 0.0
    ranges = analysis.silence_ranges(gated, store)["T0"]
    assert t0["stretches"] == len(ranges)
    assert t0["close_s"] == pytest.approx(sum(b - a for a, b in ranges) / RATE)
    assert t0["name"] == "Voice 0"
    assert gated.track("T0").gate == ((0, 10 * RATE),)


def _hand_muted(p, store, seconds):
    """``p`` with clip pieces muted where the default method closes, in the
    first ``seconds``: a stand-in for the owner's hand mutes."""
    for track_id, ranges in analysis.silence_ranges(p, store).items():
        cut = [(a, min(b, seconds * RATE)) for a, b in ranges if a < seconds * RATE]
        p = ops.mute_ranges(p, track_id, cut)
    return p


def test_the_compensated_method_needs_hand_mutes():
    p, store = conversation(seconds=60, bleed=0.3)
    with pytest.raises(ops.EditError) as e:
        analysis.silence_ranges(p, store, SilenceOptions(method="compensated"))
    assert e.value.key == "error.silence.no_hand_mutes"
    assert analysis.calibration_end(p) == 0


def test_the_compensated_method_learns_from_the_hand_mutes_and_leaves_them_out():
    p, store = conversation(seconds=120, bleed=0.3)
    plain = analysis.preview_silence(p, store)
    marked = _hand_muted(p, store, 60)
    assert analysis.calibration_end(marked) > 0
    rows = analysis.preview_silence(marked, store, SilenceOptions(method="compensated"))
    assert [r["track_id"] for r in rows] == ["T0", "T1", "T2", "T3"]
    got = sum(r["close_s"] for r in rows)
    want = sum(r["close_s"] for r in plain)
    assert 0.6 * want < got < 1.4 * want
    # the measurement ignores the mutes: same answer as with none, for the
    # default method too
    assert analysis.silence_ranges(marked, store) == analysis.silence_ranges(
        marked, store, SilenceOptions())
