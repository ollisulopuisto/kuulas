"""The sync anchor, "sync the selection", and the track a clip came from.

Tracks: A (Anna), V (Ville), Z (Zoom, the group's main = the anchor).
"""

from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

from kuulas import edit_scope, ops, sync_state
from kuulas.model import Clip
from kuulas.session import Session

RATE = 48000
SEC = 10


def _wav(path, seed):
    rng = np.random.default_rng(seed)
    sf.write(path, (rng.standard_normal(SEC * RATE) * 0.1).astype(np.float32), RATE,
             subtype="PCM_16")
    return str(path)


@pytest.fixture
def s(tmp_path):
    session = Session(tmp_path / "Talk.kuulas")
    session.import_media([_wav(tmp_path / f"{n}.wav", i) for i, n in enumerate("avz")])
    p = session.state
    session.names = dict(zip("AVZ", [t.id for t in p.tracks], strict=True))
    session.clip_of = {k: p.track(v).clips[0].id for k, v in session.names.items()}
    for k, name in zip("AVZ", ("Anna", "Ville", "Zoom"), strict=True):
        session.edit("set_track", {"track_id": session.names[k], "name": name})
    session.edit("mark_in_sync", {"clip_ids": list(session.clip_of.values()),
                                  "main": session.clip_of["Z"], "group_id": "g"})
    yield session
    session.close()


def media_of(s, k):
    return s.state.clip(s.clip_of[k]).media


def states(p):
    return {c.id: sync_state.sync_state(p, c) for t in p.tracks for c in t.clips}


def move(s, clip_id, direction):
    s.edit("move_clips_to_track", {"clip_ids": [clip_id], "direction": direction,
                                   "group_editing": False})


def drift(s, k, delta=2400):
    s.edit("nudge_clips", {"clip_ids": [s.clip_of[k]], "delta": delta,
                           "group_editing": False})


# -- B: choosing the anchor ----------------------------------------------------


def test_set_anchor_makes_the_clips_media_the_main_and_moves_nothing(s):
    drift(s, "V")
    s.edit("set_free", {"clip_ids": [s.clip_of["A"]], "free": True})
    before = s.state
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["A"]})
    assert s.state.sync_group(media_of(s, "A")).main == media_of(s, "A")
    assert s.state.tracks == before.tracks
    # In sync, drift and free are all as they were.
    assert states(s.state) == states(before)


def test_set_anchor_keeps_what_is_in_sync_in_sync(s):
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["V"]})
    assert sync_state.overview(s.state) == []


def test_resync_after_a_new_anchor_goes_relative_to_it(s):
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["V"]})
    drift(s, "V", 9600)
    drifting = {d.clip_id for d in sync_state.drifts(s.state)}
    assert drifting == {s.clip_of["A"], s.clip_of["Z"]}
    s.command("resync", {"clip_ids": [s.clip_of["A"], s.clip_of["Z"]]})
    assert s.state.clip(s.clip_of["A"]).start == 9600
    assert s.state.clip(s.clip_of["Z"]).start == 9600


def test_the_old_anchor_is_a_follower_after_the_change(s):
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["A"]})
    drift(s, "Z")
    assert sync_state.sync_state(s.state, s.clip_of["Z"]).offset == 2400
    s.command("resync", {"clip_ids": [s.clip_of["Z"]]})
    assert s.state.clip(s.clip_of["Z"]).start == 0


def test_free_clips_stay_free_after_a_new_anchor(s):
    s.edit("set_free", {"clip_ids": [s.clip_of["V"]], "free": True})
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["A"]})
    assert sync_state.sync_state(s.state, s.clip_of["V"]).state == "free"


def test_set_anchor_is_undoable(s):
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["A"]})
    s.undo()
    assert s.state.sync_group(media_of(s, "A")).main == media_of(s, "Z")


def test_set_anchor_on_the_anchor_changes_nothing(s):
    assert ops.set_sync_anchor(s.state, s.clip_of["Z"]) == s.state


def test_set_anchor_without_a_group_fails(s):
    bare = replace(s.state, sync_groups=())
    with pytest.raises(ops.EditError):
        ops.set_sync_anchor(bare, s.clip_of["A"])


def test_anchors_lists_the_anchor_pieces_with_their_track_names(s):
    assert s.sync_anchors() == [{"clip_id": s.clip_of["Z"], "track_id": s.names["Z"],
                                 "name": "Zoom", "group": "g"}]
    s.edit("set_sync_anchor", {"clip_id": s.clip_of["A"]})
    assert [a["name"] for a in s.sync_anchors()] == ["Anna"]


# -- C: sync the selection, and say what happened ---------------------------------


def test_a_single_clip_that_is_not_the_anchor_syncs_to_it(s):
    drift(s, "A")
    s.command("resync", {"clip_ids": [s.clip_of["A"]]})
    r = s.last_resync
    assert (r["kind"], r["resynced"]) == ("synced", 1)
    assert r["message"].startswith("Synced 1 clip to Zoom")
    assert "tracks unchanged" in r["message"]
    assert s.state.clip(s.clip_of["A"]).start == 0


def test_selection_with_anchor_and_others_moves_only_the_others(s):
    drift(s, "A")
    drift(s, "V", 4800)
    s.command("resync", {"clip_ids": [s.clip_of[k] for k in "ZAV"]})
    assert s.last_resync["resynced"] == 2
    assert s.last_resync["message"].startswith("Synced 2 clips to Zoom")


def test_already_in_sync_says_nothing_to_do(s):
    s.command("resync", {"clip_ids": [s.clip_of["A"]]})
    assert s.last_resync["kind"] == "nothing"
    assert s.last_resync["message"] == "Nothing to do, already in sync"


def test_selecting_only_the_anchor_says_so(s):
    s.command("resync", {"clip_ids": [s.clip_of["Z"]]})
    assert s.last_resync["kind"] == "anchor"
    assert s.last_resync["message"] == "Selection contains the anchor, nothing to move"


def test_a_noop_resync_makes_no_history_step(s):
    head = s.history.head
    s.command("resync", {"clip_ids": [s.clip_of["A"]]})
    assert s.history.head == head


def test_a_clip_outside_every_group_says_so(s, tmp_path):
    s.import_media([_wav(tmp_path / "m.wav", 9)])
    loose = s.state.tracks[-1].clips[0].id
    s.command("resync", {"clip_ids": [loose]})
    assert s.last_resync["kind"] == "ungrouped"
    assert s.last_resync["message"] == "The selection is not in a sync group"


# -- the track a clip came from -------------------------------------------------


def test_moving_to_another_track_remembers_the_home_track(s):
    a = s.clip_of["A"]
    move(s, a, 1)
    c, t = s.state.clip_and_track(a)
    assert t.id == s.names["V"]
    assert c.home == s.names["A"]
    # Resync is time only: the clip stays on the track it is on.
    s.command("resync", {"clip_ids": [a]})
    assert s.state.clip_and_track(a)[1].id == s.names["V"]


def test_moving_back_forgets_it_and_a_split_piece_inherits_it(s):
    a = s.clip_of["A"]
    move(s, a, 1)
    p = ops.split_clip(s.state, a, 5 * RATE)
    pieces = [c for c in p.track(s.names["V"]).clips if c.media == media_of(s, "A")]
    assert len(pieces) == 2
    assert all(c.home == s.names["A"] for c in pieces)
    move(s, a, -1)
    assert s.state.clip(a).home is None


def test_put_back_on_its_original_track_keeps_the_time_and_is_undoable(s):
    a = s.clip_of["A"]
    drift(s, "A")
    move(s, a, 1)
    start = s.state.clip(a).start
    s.edit("send_home", {"clip_ids": [a]})
    c, t = s.state.clip_and_track(a)
    assert (t.id, c.start, c.home) == (s.names["A"], start, None)
    s.undo()
    assert s.state.clip_and_track(a)[1].id == s.names["V"]


def test_send_home_skips_clips_that_never_moved(s):
    assert ops.send_home(s.state, [s.clip_of["A"]]) == s.state


def test_home_is_written_only_when_set():
    plain = Clip(id="c", media="m", start=0, offset=0, length=1)
    assert "home" not in plain.to_dict()
    assert Clip.from_dict(replace(plain, home="t1").to_dict()).home == "t1"


# -- a clip moved onto another group track -------------------------------------


def _moved_onto_z(s):
    a = s.clip_of["A"]
    p = ops.nudge_clips(s.state, [a], 20 * RATE)
    return ops.move_clip(p, a, p.clip(a).start, s.names["Z"])


def test_a_clip_moved_onto_its_partners_track_is_still_a_partner(s):
    z, a = s.clip_of["Z"], s.clip_of["A"]
    p = _moved_onto_z(s)
    assert {c.id for c in edit_scope.partners(p, None, a)} == {z, s.clip_of["V"]}
    assert a in [c.id for c in edit_scope.partners(p, None, z)]
    wide = edit_scope.expand_clips(p, None, [a], True)
    assert wide.count(a) == 1
    assert z in wide


def test_drift_of_a_clip_on_the_anchors_track_is_measured_against_the_anchor(s):
    a = s.clip_of["A"]
    p = _moved_onto_z(s)
    assert sync_state.sync_state(p, a).offset == 20 * RATE
    assert ops.resync(p, [a]).clip(a).start == 0
