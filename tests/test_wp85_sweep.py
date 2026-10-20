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
    assert "recommendation" in text
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
