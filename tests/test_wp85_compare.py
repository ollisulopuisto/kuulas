"""WP85 compare spike (scripts/spikes/wp85_compare.py): interval maths and an
end-to-end run on two synthetic projects."""

import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "spikes"))
import wp85_compare as wc

from kuulas.session import Session

RATE = 8000
SEC = 12


def test_interval_maths():
    assert wc.merge([(5, 8), (0, 3), (2, 4)]) == [(0, 4), (5, 8)]
    assert wc.intersect([(0, 10)], [(2, 4), (8, 12)]) == [(2, 4), (8, 10)]
    assert wc.subtract([(0, 10)], [(2, 4), (8, 12)]) == [(0, 2), (4, 8)]
    assert wc.subtract([(0, 5)], []) == [(0, 5)]
    c = wc.compare_track([(0, 6)], [(3, 9)], [(0, 12)], 12)
    assert wc.total(c["both"]) == 3
    assert c["only_pm"] == [(0, 3)]
    assert c["only_k"] == [(6, 9)]
    assert c["union"] == 9


def speech(rng, seconds):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    return (0.3 * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(n)).astype(np.float32)


def make_project(folder, src, mute):
    """``mute``: hand-made mutes in seconds per track name. Media are linked."""
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
    proc = tmp_path / "In_processed.kuulas"
    make_project(inp, src, {"Anna": [(4.5, 5.5)]})
    make_project(proc, src, {"Anna": [(5.0, 12.0)], "Ville": [(0.0, 5.0)]})
    return inp, proc


def snapshot(*dirs):
    return {p: p.read_bytes() for d in dirs for p in d.rglob("*") if p.is_file()}


def test_compare_end_to_end_and_originals_untouched(episode, tmp_path):
    inp, proc = episode
    before = snapshot(inp, proc)
    work = tmp_path / "work"
    lines = []
    res = wc.run(inp, proc, work, None,
                 out=lambda *a: lines.append(" ".join(map(str, a))))
    assert snapshot(inp, proc) == before  # nothing added, nothing changed
    anna = res["tracks"]["Anna"]
    assert anna["ref"] == pytest.approx(7.0, abs=0.01)
    assert anna["both"] > 3.0  # kuulas closes Anna while only Ville talks
    assert 0.0 < anna["jaccard"] <= 1.0
    assert anna["hand_s"] == pytest.approx(1.0, abs=0.01)
    assert res["tracks"]["Ville"]["both"] > 3.0
    assert "TOTAL" in "\n".join(lines)
    with (work / "disagreements.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert {r["direction"] for r in rows} <= {"only-podcast-magic", "only-kuulas"}
    assert all(float(r["length_s"]) > 0 for r in rows)
    saved = json.loads((work / "compare.json").read_text(encoding="utf-8"))
    assert saved["tracks"].keys() == {"Anna", "Ville"}


def test_unmatched_track_is_reported(episode, tmp_path):
    inp, proc = episode
    s = Session(inp)
    s.edit("add_track", {"track_id": "Solo", "name": "Solo"})
    s.edit("add_clip", {"track_id": "Solo", "media_id": s.state.media[0].id})
    s.close()
    lines = []
    res = wc.run(inp, proc, tmp_path / "w2", 0.1,
                 out=lambda *a: lines.append(" ".join(map(str, a))))
    assert res["unmatched"] == ["input only: Solo"]
    assert "UNMATCHED input only: Solo" in lines
