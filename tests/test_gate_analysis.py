"""Auto-Silence writes a merged gate, never clip pieces (WP44)."""

from gate_fixtures import RATE, conversation

from kuulas import analysis, gate, ops
from kuulas.history import edit_blob
from kuulas.model import Project


def test_clips_stay_whole_and_the_gate_holds_the_closed_stretches():
    p, store = conversation()
    q = analysis.auto_silence(p, store)
    for i in range(4):
        assert q.track(f"T{i}").clips == p.track(f"T{i}").clips
        assert q.track(f"T{i}").gate
        assert gate.normalise(q.track(f"T{i}").gate) == q.track(f"T{i}").gate


def test_the_gate_is_a_fraction_of_the_clip_pieces_it_replaces():
    p, store = conversation()
    ranges = analysis.silence_ranges(p, store)
    pieced = p
    for track_id, r in ranges.items():
        pieced = ops.mute_ranges(pieced, track_id, r)
    pieces = sum(len(t.clips) for t in pieced.tracks)
    gated = sum(len(r) for r in ranges.values())
    raw = sum(len(r) for r in analysis.raw_silence_ranges(p, store).values())
    # Measured on this fixture (300 s, 4 mics): 198 raw toggles, 198 gate
    # ranges (the fixture has no stretch the merge would bridge), against 393
    # clip pieces; the state packs to 1.7 KB with the gate and 8.1 KB with the
    # pieces. A 1-hour session scales both by 12.
    assert gated <= raw
    assert pieces > 1.9 * gated  # two splits per range, fewer at the ends
    gate_bytes = len(edit_blob(analysis.auto_silence(p, store))[1])
    assert gate_bytes * 3 < len(edit_blob(pieced)[1])


def test_running_it_again_replaces_the_gate():
    p, store = conversation(seconds=120)
    once = analysis.auto_silence(p, store)
    twice = analysis.auto_silence(once, store)
    assert [t.gate for t in twice.tracks] == [t.gate for t in once.tracks]
    assert [t.clips for t in twice.tracks] == [t.clips for t in once.tracks]


def test_a_second_run_replaces_a_stale_gate_even_where_it_was_wrong():
    p, store = conversation(seconds=120)
    wrong = ops.set_gate(p, "T0", [(0, 100 * RATE)])
    again = analysis.auto_silence(wrong, store)
    assert again.track("T0").gate == analysis.auto_silence(p, store).track("T0").gate


def test_track_ids_limit_which_gates_are_written():
    p, store = conversation(seconds=120)
    q = analysis.auto_silence(p, store, ["T1"])
    assert q.track("T1").gate
    assert q.track("T0").gate == ()


def test_short_open_and_closed_stretches_are_merged(monkeypatch):
    p, store = conversation(seconds=30)
    mo, mc = round(analysis.MIN_OPEN_S * RATE), round(analysis.MIN_CLOSED_S * RATE)
    raw = ((0, 4000), (4000 + mo - 1, 20000), (30000, 30000 + mc - 1),
           (40000, 60000))
    monkeypatch.setattr(analysis, "raw_silence_ranges", lambda *_: {"T0": raw})
    assert analysis.silence_ranges(p, store)["T0"] == ((0, 20000), (40000, 60000))


def test_the_constants_are_the_owners_starting_values():
    assert (analysis.MIN_OPEN_S, analysis.MIN_CLOSED_S) == (0.4, 0.3)


def test_an_existing_gate_does_not_hide_the_audio_it_is_decided_from():
    p, store = conversation(seconds=60)
    gated = ops.set_gate(p, "T0", [(0, 60 * RATE)])
    assert analysis.silence_ranges(gated, store) == analysis.silence_ranges(p, store)
    assert isinstance(p, Project)
