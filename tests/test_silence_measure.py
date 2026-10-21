"""Auto-Silence in two stages (the live preview): MEASURE once per audio state,
then DECIDE per options in milliseconds. The split must not change a single
range: every answer is checked against the goldens recorded from the code
before the split (``silence_golden_cases``)."""

import hashlib
import json
import pickle
import time
from dataclasses import replace

import numpy as np
import pytest
from gate_fixtures import RATE, conversation
from silence_golden_cases import GOLDEN, projects

from kuulas import analysis, ops
from kuulas.model import Clip, Media, Project
from kuulas.silence_options import SilenceOptions


def _as_json(ranges):
    return {k: [list(r) for r in v] for k, v in ranges.items()}


def _gates(p):
    return {t.id: t.gate for t in p.tracks}


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def proven(**kwargs):
    """``conversation`` with a SHA-256 on every media, as an imported file has
    (without one a key proves nothing and never matches)."""
    p, store = conversation(**kwargs)
    return replace(p, media=tuple(replace(m, sha256=_sha(m.id)) for m in p.media)), store


def test_media_without_a_sha256_never_gives_a_matching_key():
    p, _ = conversation(seconds=5)
    assert analysis.silence_key(p) != analysis.silence_key(p)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


@pytest.fixture(scope="module")
def cases():
    return projects()


def test_silence_ranges_still_gives_the_recorded_answers(cases, golden):
    for name, (p, store, option_sets) in cases.items():
        for opt_name, opts in option_sets.items():
            got = _as_json(analysis.silence_ranges(p, store, opts))
            assert got == golden[f"{name}/{opt_name}"], f"{name}/{opt_name}"


def test_measure_then_decide_gives_the_recorded_answers(cases, golden):
    for name, (p, store, option_sets) in cases.items():
        measure = analysis.measure_silence(p, store)
        for opt_name, opts in option_sets.items():
            got = analysis.silence_ranges_from(measure, opts, _gates(p))
            assert _as_json(got) == golden[f"{name}/{opt_name}"], f"{name}/{opt_name}"


def test_the_per_track_measure_equals_the_whole_measure():
    p, store = proven(seconds=40)
    whole = analysis.measure_silence(p, store)
    levels = {tid: analysis.measure_silence_track(p, store, tid)
              for tid in analysis.silence_measured_ids(p)}
    parts = analysis.assemble_measure(p, levels)
    assert parts.key == whole.key
    assert parts.tracks == whole.tracks
    for tid, lv in whole.levels.items():
        assert np.array_equal(parts.levels[tid].db, lv.db)
        assert np.array_equal(parts.levels[tid].valid, lv.valid)
        assert parts.levels[tid].floor == lv.floor


def test_the_compensated_method_still_needs_hand_mutes():
    p, store = proven(seconds=30)
    measure = analysis.measure_silence(p, store)
    with pytest.raises(ops.EditError) as e:
        analysis.silence_ranges_from(measure, SilenceOptions(method="compensated"))
    assert e.value.key == "error.silence.no_hand_mutes"


def test_the_measure_does_not_see_the_gate_and_its_key_ignores_it():
    p, store = proven(seconds=30)
    gated = ops.set_gate(p, "T0", [(0, 10 * RATE)])
    a, b = analysis.measure_silence(p, store), analysis.measure_silence(gated, store)
    assert a.key == b.key == analysis.silence_key(p) == analysis.silence_key(gated)
    assert np.array_equal(a.levels["T0"].db, b.levels["T0"].db)


def test_the_key_follows_what_the_speech_audio_depends_on():
    p, _ = proven(seconds=30)
    key = analysis.silence_key(p)
    same = [
        ops.set_gate(p, "T1", [(0, RATE)]),
        ops.set_track(p, "T1", gain_db=-6.0),
        ops.set_clip(p, "c1", gain_db=3.0),
        ops.set_track_automation(p, "T2", [(0, -3.0), (RATE, 0.0)]),
    ]
    for q in same:
        assert analysis.silence_key(q) == key
    different = [
        ops.trim_clip(p, "c1", start=RATE),
        ops.set_track(p, "T1", mute=True),
        ops.set_track(p, "T1", speaker="Ann"),
        ops.set_clip(p, "c1", muted=True),
        ops.move_track(p, "T3", 0),
        replace(p, media=tuple(replace(m, sha256="f" * 64) if m.id == "m1" else m
                               for m in p.media)),
    ]
    for q in different:
        assert analysis.silence_key(q) != key


def test_a_music_track_matters_only_through_the_length():
    p, _ = proven(seconds=30)
    key = analysis.silence_key(p)
    p = ops.add_media(p, Media(id="mm", name="m.wav", channels=1, frames=60 * RATE))
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    inside = ops.add_clip(p, track_id="M", media_id="mm", clip_id="cm", length=10 * RATE)
    assert analysis.silence_key(inside) == key
    longer = ops.add_clip(p, track_id="M", media_id="mm", clip_id="cm", length=60 * RATE)
    assert analysis.silence_key(longer) != key


def test_the_measure_pickles():
    p, store = proven(seconds=20)
    m = analysis.measure_silence(p, store)
    # The worker hands results back pickled; this is our own object.
    back = pickle.loads(pickle.dumps(m))  # noqa: S301 - our own bytes, made just above
    assert back.key == m.key
    assert analysis.silence_ranges_from(back) == analysis.silence_ranges_from(m)


def test_rows_summarise_the_ranges():
    p, store = proven(seconds=30)
    gated = ops.set_gate(p, "T0", [(0, 5 * RATE)])
    m = analysis.measure_silence(gated, store)
    ranges = analysis.silence_ranges_from(m)
    rows = analysis.silence_rows(m, ranges, _gates(gated))
    assert [r["track_id"] for r in rows] == ["T0", "T1", "T2", "T3"]
    r0 = rows[0]
    assert r0["name"] == "Voice 0"
    assert r0["ranges"] == [list(r) for r in ranges["T0"]]
    assert r0["stretches"] == len(ranges["T0"])
    assert r0["close_s"] == pytest.approx(sum(b - a for a, b in ranges["T0"]) / RATE)
    assert r0["now_s"] == 5.0
    assert r0["total_s"] == pytest.approx(p.length / RATE)


# -- cost: what a slider move costs on a long project ----------------------------------


def _long_measure(minutes=45, bleed=0.5):
    """A 45-minute four-mic measure: the level curves of a measured 300-second
    synthetic conversation (``gate_fixtures``: syllables, turns, backchannels,
    every mic hearing the others at ``bleed``) laid end to end. Real per-hop
    flicker, so the decision's run loops see what a real episode gives them."""
    p, store = proven(seconds=300, bleed=bleed, turn=(0.5, 3.5))
    short = analysis.measure_silence(p, store)
    reps = minutes * 60 // 300
    hop = analysis.hop_frames(RATE)
    q = Project(rate=RATE)
    levels = {}
    for i, t in enumerate(short.tracks):
        lv = short.levels[t.id]
        q = ops.add_media(q, Media(id=f"m{i}", name=f"{i}.wav", channels=1,
                                   frames=lv.db.size * reps * hop))
        q = ops.add_track(q, track_id=t.id, name=t.name)
        q = ops.add_clip(q, track_id=t.id, media_id=f"m{i}", clip_id=f"c{i}")
        levels[t.id] = (np.tile(lv.db, reps), np.tile(lv.valid, reps))
    return q, analysis.assemble_measure(q, levels)


def test_a_45_minute_four_mic_measure_is_small_and_decides_in_milliseconds():
    p, m = _long_measure()
    assert m.hops == 45 * 60 * 50
    assert isinstance(p.tracks[0].clips[0], Clip)
    # 135,000 hops x 4 mics x (4 + 1) bytes: 2.7 MB.
    assert m.nbytes < 3 * 1024 * 1024
    assert len(pickle.dumps(m)) < 4 * 1024 * 1024
    analysis.silence_ranges_from(m)  # warm up
    timings = []
    for margin in (8.0, 12.0, 16.0):
        # CPU time of this thread: other work on a busy machine does not count.
        began = time.thread_time()
        ranges = analysis.silence_ranges_from(m, SilenceOptions(margin_db=margin))
        timings.append(time.thread_time() - began)
        assert set(ranges) == {"T0", "T1", "T2", "T3"}
    # Measured 80 to 100 ms on the Mac Studio (M1 Max) under load, most of it
    # in speechmix's run loops (the note in ``analysis``). The target is under
    # 100 ms; the bound leaves room for a slower or busier machine, and still
    # fails if the decision ever starts reading audio or looping over hops.
    assert min(timings) < 0.25, timings
