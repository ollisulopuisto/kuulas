"""Edit groups (WP19a) and free-vs-drift sync states (R51), through the Session.

Scenes are numbered as in the storyboard (docs/ui-sketches.html). Tracks:
A (Anna), V (Ville), Z (Zoom, the group's main), M (music, in no group).
"""

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from kuulas import ops, sync_state
from kuulas.model import Clip
from kuulas.server import create_app
from kuulas.session import Session

RATE = 48000
SEC = 10  # seconds of each recording


def _wav(path, seed):
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(SEC * RATE) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return str(path)


@pytest.fixture
def s(tmp_path):
    session = Session(tmp_path / "Talk.kuulas")
    paths = [_wav(tmp_path / f"{n}.wav", i) for i, n in enumerate(("a", "v", "z", "m"))]
    session.import_media(paths[:3])
    session.import_media(paths[3:])  # a second import: music has a clock of its own
    p = session.state
    ids = [t.id for t in p.tracks]
    names = dict(zip(("A", "V", "Z", "M"), ids, strict=True))
    session.names = names
    session.clip_of = {k: p.track(v).clips[0].id for k, v in names.items()}
    # Rename the tracks to the short ids by looking them up; keep the real ids.
    main = session.clip_of["Z"]
    session.edit("mark_in_sync", {"clip_ids": [session.clip_of[k] for k in "AVZ"],
                                  "main": main, "group_id": "g"})
    session.edit("set_track", {"track_id": names["M"], "kind": "music"})
    yield session
    session.close()


def clips_on(s, key):
    return s.state.track(s.names[key]).clips


def span(s, key):
    cs = clips_on(s, key)
    return [(c.start, c.end) for c in cs]


GAP = (4 * RATE, 5 * RATE + RATE // 5)  # 1.2 s


def test_scene1_range_cut_expands_to_the_group_and_not_to_music(s):
    t = s.edit_target("cut", {"track_ids": [s.names["A"]], "start": GAP[0],
                              "end": GAP[1]})
    assert set(t["track_ids"]) == {s.names[k] for k in "AVZ"}
    s.edit("cut_range", {"start": GAP[0], "end": GAP[1], "track_ids": [s.names["A"]]})
    cut = GAP[1] - GAP[0]
    for k in "AVZ":
        assert clips_on(s, k)[-1].end == SEC * RATE - cut
    assert clips_on(s, "M")[-1].end == SEC * RATE  # music is not in the group
    assert sync_state.drifts(s.state) == []


def test_scene2_grouping_off_cuts_only_the_focused_track_and_shows_drift(s):
    s.set_group_editing(False)
    t = s.edit_target("cut", {"track_ids": [s.names["A"]], "start": GAP[0],
                              "end": GAP[1]})
    assert t["track_ids"] == [s.names["A"]]
    s.edit("cut_range", {"start": GAP[0], "end": GAP[1], "track_ids": [s.names["A"]]})
    cut = GAP[1] - GAP[0]
    assert clips_on(s, "V")[-1].end == SEC * RATE
    late = clips_on(s, "A")[-1]
    state = s.sync_state(late.id)
    assert (state.state, state.offset) == ("drift", -cut)
    assert [d["clip_id"] for d in s.drift_list()] == [late.id]
    # ... and the cause is read from history, with group editing off.
    cause = s.sync_cause(late.id)
    assert cause["op"] == "cut_range"
    assert cause["group_editing"] is False
    assert cause["track_id"] == s.names["A"]


def test_scene3_gain_on_chosen_clips_touches_exactly_those(s):
    chosen = [s.clip_of["A"], s.clip_of["M"]]
    assert s.edit_target("gain", {"clip_ids": chosen})["clip_ids"] == chosen
    s.edit("adjust_clip_gain", {"clip_ids": chosen, "delta_db": 2.0})
    gains = {k: clips_on(s, k)[0].gain_db for k in "AVZM"}
    assert gains == {"A": 2.0, "V": 0.0, "Z": 0.0, "M": 2.0}


def test_scene4_nudging_one_clip_moves_its_partners(s):
    a = s.clip_of["A"]
    wide = s.edit_target("nudge", {"clip_ids": [a]})["clip_ids"]
    assert set(wide) == {s.clip_of[k] for k in "AVZ"}
    s.edit("nudge_clips", {"clip_ids": [a], "delta": 2400})
    assert [clips_on(s, k)[0].start for k in "AVZ"] == [2400] * 3
    assert clips_on(s, "M")[0].start == 0
    assert sync_state.drifts(s.state) == []


def test_scene4_nudge_with_grouping_off_moves_one_and_shows_drift(s):
    s.set_group_editing(False)
    a = s.clip_of["A"]
    s.edit("nudge_clips", {"clip_ids": [a], "delta": 2400})
    assert clips_on(s, "V")[0].start == 0
    assert [(d["clip_id"], d["offset"]) for d in s.drift_list()] == [(a, 2400)]


def test_scene5_backspace_leaves_a_gap_and_shifts_nothing(s):
    s.edit("split_clips", {"at": GAP[0], "clip_ids": [s.clip_of["A"]]})
    s.edit("split_clips", {"at": GAP[1], "clip_ids": [clips_on(s, "A")[1].id]})
    cough = clips_on(s, "A")[1].id
    assert s.edit_target("delete", {"clip_ids": [cough]})["clip_ids"] == [cough]
    before = span(s, "V"), span(s, "Z")
    s.edit("delete_clips", {"clip_ids": [cough]})
    assert (span(s, "V"), span(s, "Z")) == before
    assert span(s, "A") == [(0, GAP[0]), (GAP[1], SEC * RATE)]
    assert s.drift_list() == []


def test_scene6_resync_then_close_gap_equals_the_group_wide_cut(s):
    cut = GAP[1] - GAP[0]
    s.set_group_editing(False)
    s.edit("cut_range", {"start": GAP[0], "end": GAP[1], "track_ids": [s.names["A"]]})
    s.set_group_editing(True)
    s.command("resync_from", {"frame": GAP[0]})
    assert s.last_resync["resynced"] == 1
    assert s.drift_list() == []
    # Anna is back, with the hole where her cut was.
    assert span(s, "A")[-1] == (GAP[1], SEC * RATE)
    s.edit("ripple_delete", {"start": GAP[0], "end": GAP[1],
                             "track_ids": [s.names["A"]]})
    after = {k: span(s, k) for k in "AVZ"}
    joined = [(0, GAP[0]), (GAP[0], SEC * RATE - cut)]
    assert after["A"] == after["V"] == after["Z"] == joined


def test_scene6_reference_equals_scene1(s, tmp_path):
    """The same project cut group-wide in one go gives the same clips."""
    other = Session(tmp_path / "Other.kuulas")
    try:
        other.import_media([str(tmp_path / f"{n}.wav") for n in ("a", "v", "z", "m")])
        ids = [t.id for t in other.state.tracks]
        clips = [other.state.track(i).clips[0].id for i in ids]
        other.edit("mark_in_sync", {"clip_ids": clips[:3], "main": clips[2]})
        other.edit("cut_range", {"start": GAP[0], "end": GAP[1], "track_ids": [ids[0]]})
        group_wide = [[(c.start, c.end, c.offset) for c in other.state.track(i).clips]
                      for i in ids[:3]]
    finally:
        other.close()
    s.set_group_editing(False)
    s.edit("cut_range", {"start": GAP[0], "end": GAP[1], "track_ids": [s.names["A"]]})
    s.set_group_editing(True)
    s.command("resync_from", {"frame": GAP[0]})
    s.edit("ripple_delete", {"start": GAP[0], "end": GAP[1], "track_ids": [s.names["A"]]})
    mine = [[(c.start, c.end, c.offset) for c in clips_on(s, k)] for k in "AVZ"]
    assert mine == group_wide


def test_partners_are_found_by_recording_time_not_timeline_overlap(s):
    # Move Ville's clip far away in time; it is still Anna's partner.
    s.set_group_editing(False)
    s.edit("nudge_clips", {"clip_ids": [s.clip_of["V"]], "delta": 3 * RATE})
    wide = s.edit_target("nudge", {"clip_ids": [s.clip_of["A"]]}, True)["clip_ids"]
    assert s.clip_of["V"] in wide
    # A clip of the same group on another stretch of the recording is not.
    s.edit("split_clips", {"at": 5 * RATE, "clip_ids": [s.clip_of["Z"]]})
    late_z = clips_on(s, "Z")[1].id
    assert late_z not in wide


def test_group_editing_toggle_is_session_state_not_history(s):
    nodes = len(s.history.nodes())
    s.set_group_editing(False)
    s.set_group_editing(True)
    assert len(s.history.nodes()) == nodes
    assert s.group_editing is True
    s.undo()  # undo steps the edits, not the switch
    s.set_group_editing(False)
    s.undo()
    assert s.group_editing is False


def test_ripple_trim_with_grouping_off_shifts_only_its_track(s):
    a = s.clip_of["A"]
    s.edit("split_clips", {"at": 4 * RATE, "clip_ids": [a]})
    first = clips_on(s, "A")[0].id
    s.set_group_editing(False)
    s.edit("ripple_trim", {"clip_id": first, "edge": "end", "frame": 3 * RATE})
    assert clips_on(s, "V")[0].end == SEC * RATE
    assert clips_on(s, "A")[-1].start == 3 * RATE
    s.set_group_editing(True)


def test_ripple_trim_with_grouping_on_keeps_the_group_together(s):
    for k in "AVZ":
        s.edit("split_clips", {"at": 4 * RATE, "clip_ids": [s.clip_of[k]]})
    first = clips_on(s, "A")[0].id
    s.edit("ripple_trim", {"clip_id": first, "edge": "end", "frame": 3 * RATE})
    assert [clips_on(s, k)[-1].end for k in "AVZ"] == [SEC * RATE - RATE] * 3
    assert clips_on(s, "M")[-1].end == SEC * RATE


def test_cut_words_follows_the_edit_target(s):
    rows = []
    for k in "AVZ":
        media = s.state.track(s.names[k]).clips[0].media
        rows.append(media)
    words = [{"w": "one", "s": 1.0, "e": 1.4, "p": 0.9},
             {"w": "two", "s": 4.0, "e": 5.2, "p": 0.9},
             {"w": "three", "s": 6.0, "e": 6.4, "p": 0.9}]
    s.set_transcript(rows[0], words, "t")
    idx = next(i for i, w in enumerate(s.timeline_words()) if w["w"] == "two")
    s.set_group_editing(False)
    s.command("cut_words", {"indices": [idx]})
    assert clips_on(s, "V")[-1].end == SEC * RATE  # only Anna's track was cut
    assert [d["track_id"] for d in s.drift_list()] == [s.names["A"]]
    s.undo()
    s.set_group_editing(True)
    s.command("cut_words", {"indices": [idx]})
    assert clips_on(s, "V")[-1].end == clips_on(s, "A")[-1].end < SEC * RATE
    assert clips_on(s, "M")[-1].end == SEC * RATE
    assert s.drift_list() == []


# -- R51: free vs drift ----------------------------------------------------------


def drifted(s):
    s.set_group_editing(False)
    a = s.clip_of["A"]
    s.edit("nudge_clips", {"clip_ids": [a], "delta": 14400})  # +300 ms
    return a


def test_u_toggles_free_and_a_free_clip_never_shows_drift(s):
    a = drifted(s)
    assert s.sync_state(a).state == "drift"
    s.edit("set_free", {"clip_ids": [a]})
    st = s.sync_state(a)
    assert (st.state, st.offset) == ("free", 14400)  # "+300 ms · free"
    assert s.drift_list() == []
    s.edit("set_free", {"clip_ids": [a]})  # U again re-links it
    assert s.sync_state(a).state == "drift"


def test_a_free_clip_is_no_ones_partner(s):
    a = s.clip_of["A"]
    s.edit("set_free", {"clip_ids": [a]})
    wide = s.edit_target("nudge", {"clip_ids": [s.clip_of["V"]]})["clip_ids"]
    assert a not in wide
    assert s.edit_target("nudge", {"clip_ids": [a]})["clip_ids"] == [a]


def test_pieces_split_from_a_free_clip_stay_free(s):
    a = s.clip_of["A"]
    s.edit("set_free", {"clip_ids": [a]})
    s.edit("split_clips", {"at": 5 * RATE, "clip_ids": [a]})
    assert all(c.free for c in clips_on(s, "A"))


def test_resync_skips_free_clips_and_says_so(s):
    s.set_group_editing(False)
    a, v = s.clip_of["A"], s.clip_of["V"]
    s.edit("nudge_clips", {"clip_ids": [a], "delta": 14400})
    s.edit("nudge_clips", {"clip_ids": [v], "delta": 4800})
    s.edit("set_free", {"clip_ids": [v]})
    s.command("resync_from", {"frame": 0})
    assert s.last_resync["resynced"] == 1
    assert s.last_resync["skipped"] == 1
    assert s.last_resync["message"].startswith("Synced 1 clip to ")
    assert s.last_resync["message"].endswith("skipped 1 free")
    assert clips_on(s, "A")[0].start == 0
    assert clips_on(s, "V")[0].start == 4800  # free: left alone


def test_nothing_resyncs_by_itself(s):
    a = drifted(s)
    s.edit("adjust_clip_gain", {"clip_ids": [a], "delta_db": 1.0})
    s.set_group_editing(True)
    assert clips_on(s, "A")[0].start == 14400


def test_drift_list_is_in_timeline_order_and_has_causes(s):
    s.set_group_editing(False)
    s.edit("nudge_clips", {"clip_ids": [s.clip_of["V"]], "delta": 2400})
    s.edit("nudge_clips", {"clip_ids": [s.clip_of["A"]], "delta": 4800})
    rows = s.drift_list(with_cause=True)
    assert [r["track_id"] for r in rows] == [s.names["V"], s.names["A"]]
    assert [r["offset"] for r in rows] == [2400, 4800]
    assert all(r["cause"]["group_editing"] is False for r in rows)
    assert rows[0]["cause"]["op"] == "nudge_clips"


def test_the_free_flag_round_trips_and_is_not_written_when_off(s):
    c = clips_on(s, "A")[0]
    assert "free" not in c.to_dict()
    p = ops.set_free(s.state, [c.id], True)
    d = p.clip(c.id).to_dict()
    assert d["free"] is True
    assert Clip.from_dict(d).free is True


def test_the_page_can_read_drift_and_switch_group_editing(s, tmp_path):
    class NoEngine:
        def status(self):
            return {"playing": False, "position": 0, "until": None, "notices": []}

    ui = tmp_path / "ui"
    ui.mkdir()
    with TestClient(create_app(s, NoEngine(), language="en", ui_dir=ui)) as c:
        assert c.get("/api/group-editing").json() == {"on": True}
        assert c.post("/api/group-editing", json={"on": False}).json() == {"on": False}
        assert s.group_editing is False
        a = s.clip_of["A"]
        s.edit("nudge_clips", {"clip_ids": [a], "delta": 2400})
        rows = c.get("/api/drift", params={"cause": True}).json()["drift"]
        assert [(r["clip_id"], r["offset"]) for r in rows] == [(a, 2400)]
        assert rows[0]["cause"]["group_editing"] is False
        r = c.post("/api/command", json={"name": "resync", "args": {"clip_ids": [a]}})
        assert r.json()["resync"]["resynced"] == 1
        assert c.get("/api/drift").json() == {"drift": []}
        s.edit("nudge_clips", {"clip_ids": [a], "delta": 2400})
        s.edit("set_free", {"clip_ids": [a]})
        sync = c.get("/api/sync").json()["clips"]
        assert [(r["clip_id"], r["state"], r["offset"]) for r in sync] == [
            (a, "free", 2400)]
        v = s.clip_of["V"]
        got = c.get("/api/partners", params={"ids": f"{v},nope"}).json()["partners"]
        assert got[v] == [s.clip_of["Z"]]  # A is free: no partner
        assert got["nope"] == []
        # A free clip is not drifting, so it has no cause.
        assert c.get(f"/api/sync-cause/{a}").json() == {"cause": None}


def test_sync_overview_lists_drift_and_free_clips_for_the_badges(s):
    a, v = s.clip_of["A"], s.clip_of["V"]
    s.set_group_editing(False)
    s.edit("nudge_clips", {"clip_ids": [a], "delta": 14400})
    s.edit("nudge_clips", {"clip_ids": [v], "delta": 4800})
    s.edit("set_free", {"clip_ids": [v]})
    rows = {r["clip_id"]: (r["state"], r["offset"]) for r in s.sync_overview()}
    assert rows == {a: ("drift", 14400), v: ("free", 4800)}
    # The same head asked twice is the same answer (memoized on the edit state).
    assert s.sync_overview() == s.sync_overview()


def test_partners_of_gives_the_dashed_outline_set(s):
    a = s.clip_of["A"]
    got = s.partners_of([a])
    assert set(got[a]) == {s.clip_of["V"], s.clip_of["Z"]}
    s.edit("set_free", {"clip_ids": [s.clip_of["V"]]})
    assert s.partners_of([a])[a] == [s.clip_of["Z"]]
    assert s.partners_of([s.clip_of["M"]]) == {s.clip_of["M"]: []}
