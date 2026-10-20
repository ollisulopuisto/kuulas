"""WP85 sweep spike (scripts/spikes/wp85_sweep.py): the scoring maths and an
end-to-end run on a synthetic project with hand mutes."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "spikes"))
import wp85_sweep as ws
from wp85_compare import Level

from kuulas.session import Session
from kuulas.silence_options import SilenceOptions

RATE = 8000
SEC = 12


def test_parse_floats():
    assert ws.parse_floats("4, 6,8,,6") == [4.0, 6.0, 8.0]
    with pytest.raises(ValueError, match="no numbers"):
        ws.parse_floats(" , ")


def test_score_method_counts_by_time_inside_the_area():
    truth = {"a": [(0, 100)], "b": [(0, 50)]}
    span = {"a": [(0, 200)], "b": [(0, 200)]}
    closed = {"a": [(50, 150)], "b": [(0, 50), (100, 150)]}
    got = ws.score_method(closed, truth, span, 0, 120)
    a, b = got["tracks"]["a"], got["tracks"]["b"]
    assert (a["closed"], a["truth"], a["hit"], a["beyond"]) == (70, 100, 50, 20)
    assert a["precision"] == pytest.approx(50 / 70)
    assert a["recall"] == pytest.approx(0.5)
    assert (b["closed"], b["hit"], b["recall"]) == (70, 50, 1.0)
    assert got["total"]["closed"] == 140
    assert got["total"]["hit"] == 100
    assert got["total"]["truth"] == 150


def test_an_empty_truth_or_method_does_not_divide_by_zero():
    t = ws.tally(0, 0, 0)
    assert (t["precision"], t["recall"]) == (1.0, 1.0)
    assert ws.tally(10, 0, 0)["f1"] == 0.0 or ws.tally(10, 0, 0)["f1"] > 0


def test_best_picks():
    rows = [{"label": "x", "total": {"f1": 0.7, "recall": 0.95}},
            {"label": "y", "total": {"f1": 0.8, "recall": 0.6}},
            {"label": "z", "total": {"f1": 0.5, "recall": 0.99}}]
    assert ws.best_by_f1(rows)["label"] == "y"
    assert ws.best_with_recall(rows)["label"] == "x"
    assert ws.best_with_recall(rows, 0.999) is None
    assert ws.best_by_f1([]) is None


def test_plan_has_every_family_and_the_grid_is_a_product():
    steps = ws.plan([4.0, 8.0], [3.0, 6.0])
    families = [s["family"] for s in steps]
    assert families[0] == "current"
    assert families.count("margin") == 2
    assert families.count("dominance") == 2
    assert families.count("grid") == 4
    assert families.count("compensated") == 2
    assert steps[0]["options"] == SilenceOptions()


def say(lines):
    return lambda *a: lines.append(" ".join(map(str, a)))


def speech(rng, seconds):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(n)).astype(np.float32)


def make_project(folder, src, mute):
    s = Session(folder, rate=RATE)
    s.import_media([str(src / "Anna.wav"), str(src / "Ville.wav")])
    for m in s.state.media:
        name = m.name.split(".")[0]
        s.edit("add_track", {"track_id": name, "name": name})
        s.edit("add_clip", {"track_id": name, "media_id": m.id})
    for name, spans in mute.items():
        frames = [(round(a * RATE), round(b * RATE)) for a, b in spans]
        s.edit("mute_ranges", {"track_id": name, "ranges": frames})
    s.close()


@pytest.fixture
def episode(tmp_path):
    rng = np.random.default_rng(1)
    n = SEC * RATE
    anna = np.zeros(n, dtype=np.float32)
    ville = np.zeros(n, dtype=np.float32)
    anna[: 4 * RATE] = speech(rng, 4)
    ville[6 * RATE: 10 * RATE] = speech(rng, 4)
    src = tmp_path / "src"
    src.mkdir()
    for name, own, other in (("Anna", anna, ville), ("Ville", ville, anna)):
        mic = own + 0.1 * other + 0.0003 * rng.standard_normal(n).astype(np.float32)
        sf.write(src / f"{name}.wav", mic, RATE, subtype="FLOAT")
    inp = tmp_path / "In.kuulas"
    make_project(inp, src, {"Anna": [(4.5, 12.0)], "Ville": [(0.0, 5.5)]})
    return inp


def test_end_to_end_prints_a_table_and_a_recommendation(episode, tmp_path):
    lines = []
    work = tmp_path / "work"
    result = ws.run(episode, work, 3.0, [8.0, 12.0], [6.0], out=say(lines))
    assert result is not None
    text = "\n".join(lines)
    assert "recommended" in text
    assert (work / "disagreements.csv").is_file()
    assert "eaten" in text
    assert "compensated method, diagnostics" in text
    assert "Anna" in text
    assert "margin 8" in text
    assert "compensated, presence 12" in text
    labels = [r["label"] for r in result["rows"]]
    assert labels[0] == "current"
    cur = result["rows"][0]["total"]
    assert 0.0 <= cur["f1"] <= 1.0
    # the hand mutes are well chosen: the shipped method finds most of them
    assert cur["recall"] > 0.7
    saved = json.loads((work / "sweep.json").read_text())
    assert saved["hand_window_s"] == pytest.approx(12.0)
    assert saved["recommendation"]["overall"]["best_f1"] in labels


def test_holdout_scores_the_second_half_only(episode, tmp_path):
    result = ws.run(episode, tmp_path / "w", 3.0, [12.0], [6.0], holdout=True,
                    out=say([]))
    assert result["holdout"] is True
    assert result["scored_from_s"] == pytest.approx(6.0)


def test_the_original_project_is_never_touched(episode, tmp_path):
    before = {p: p.read_bytes() for p in episode.rglob("*") if p.is_file()}
    ws.run(episode, tmp_path / "w", 3.0, [12.0], [6.0], out=say([]))
    after = {p: p.read_bytes() for p in episode.rglob("*") if p.is_file()}
    assert before == after


def test_a_project_without_hand_mutes_stops_with_a_reason(tmp_path):
    rng = np.random.default_rng(2)
    src = tmp_path / "src"
    src.mkdir()
    for name in ("Anna", "Ville"):
        sf.write(src / f"{name}.wav", speech(rng, 4), RATE, subtype="FLOAT")
    folder = tmp_path / "Bare.kuulas"
    make_project(folder, src, {})
    lines = []
    got = ws.run(folder, tmp_path / "w", 3.0, [12.0], [6.0], out=say(lines))
    assert got is None
    assert any("no hand-made mutes" in x for x in lines)


def row(label, eaten, kept, truth=100, family="margin", f1=0.5):
    return {"label": label, "family": family, "options": {},
            "total": {"eaten": eaten, "kept": kept, "recall": 1 - kept / truth, "f1": f1}}


def level_of(db):
    return Level(np.full(100, db, dtype=np.float32), np.ones(100, dtype=bool), 10)


def test_tally_has_speech_eaten_and_silence_kept():
    t = ws.tally(70, 100, 50)
    assert (t["eaten"], t["kept"]) == (20, 50)
    assert t["eaten"] == t["beyond"]


def test_pareto_and_recommendation_leave_the_compensated_method_out():
    rows = [row("a", 10, 40), row("b", 20, 10), row("c", 30, 30), row("d", 5, 90),
            row("e", 0, 0, family="compensated"), row("f", 20, 10)]
    assert [r["label"] for r in ws.pareto(rows)] == ["d", "a", "b"]
    assert ws.recommended(rows, 0.8)["label"] == "b"
    assert ws.recommended(rows, 0.999) is None


def test_plan_with_knobs_and_the_combination_grid():
    steps = ws.plan([12.0], [6.0], ws.DEFAULT_KNOBS)
    fams = [s["family"] for s in steps]
    assert fams.count("min_open") == 3
    assert fams.count("min_closed") == 4
    assert fams.count("open_before") == 3
    assert fams.count("open_after") == 4
    scored = [
        {**s, "options": s["options"].as_dict(),
         "total": {"eaten": i, "kept": 0, "recall": 1.0, "f1": 0.5}}
        for i, s in enumerate(steps)]
    combos = ws.plan_combos(scored)
    assert all(c["family"] == "combo" for c in combos)
    assert 0 < len(combos) <= 2 ** 6
    assert len({c["label"] for c in combos}) == len(combos)


def test_eaten_stretches_with_levels_and_names():
    truth = {"a": [(0, 100)], "b": []}
    span = {"a": [(0, 400)], "b": [(0, 400)]}
    closed = {"a": [(50, 250)], "b": []}
    eaten = ws.eaten_ranges(closed, truth, span, 0, 300)
    assert eaten == {"a": [(100, 250)], "b": []}
    rows = ws.stretch_rows("x", eaten, {"a": level_of(-50.0), "b": level_of(-20.0)},
                           {"a": "Anna", "b": "Ville"}, 100)
    assert len(rows) == 1
    r = rows[0]
    assert (r["track"], r["loudest_other"]) == ("Anna", "Ville")
    assert r["start_s"] == 1.0
    assert r["length_s"] == 1.5
    assert r["own_db"] < r["other_db"]
    assert ws.mmss1(75.26) == "01:15.3"


def test_compensated_diagnostics_report_offsets_evidence_and_shares():
    rng = np.random.default_rng(3)
    hops = 600
    own = np.full((2, hops), -60.0)
    own[0, :200] = -20.0   # Anna talks first, Ville later
    own[1, 300:500] = -20.0
    db = own.copy()
    db[1] = np.maximum(db[1], own[0] - 12.0)   # each hears the other 12 dB down
    db[0] = np.maximum(db[0], own[1] - 12.0)
    db += rng.normal(0, 0.5, db.shape)
    valid = np.ones(db.shape, dtype=bool)
    muted = np.zeros(db.shape, dtype=bool)
    muted[1, :250] = True
    muted[0, 250:] = True
    scored = np.ones(hops, dtype=bool)
    d = ws.compensated_diagnostics(db, valid, muted, scored, muted, scored, 12.0)
    assert d["hops"][1][0] == 200
    assert d["hops"][0][1] == 200
    assert d["fallback"] == []
    assert d["offsets"][1][0] == pytest.approx(-12.0, abs=1.0)
    anna, ville = d["mics"]
    assert anna["truth_open"] == pytest.approx(250 / 600)
    assert anna["speaking_when_truth_muted"] < 0.05
    assert ville["speaking_when_truth_muted"] < 0.05
    assert anna["speaking_when_truth_open"] > 0.5
