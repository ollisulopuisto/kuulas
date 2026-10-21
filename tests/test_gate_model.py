"""Track.gate in the model and the edit vocabulary (WP44)."""

import json

import pytest

from kuulas import ops
from kuulas.history import History
from kuulas.model import Media, Project

RATE = 48000


def base():
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="a.wav", channels=1, frames=60 * RATE))
    p = ops.add_track(p, track_id="t", name="Anna")
    p = ops.add_track(p, track_id="u", name="Ville")
    return ops.add_clip(p, track_id="t", media_id="m", clip_id="c")


def test_a_track_has_no_gate_by_default():
    assert base().track("t").gate == ()


def test_gate_round_trips_through_json():
    p = ops.set_gate(base(), "t", [(10, 20), (40, 50)])
    q = Project.from_json(p.to_json())
    assert q.track("t").gate == ((10, 20), (40, 50))
    assert q == p


def test_an_old_project_without_gate_loads_and_stays_without_one_on_disk():
    d = json.loads(base().to_json())
    assert all("gate" not in t for t in d["tracks"])
    q = Project.from_dict(d)
    assert q.track("t").gate == ()
    # Nothing is written for an empty gate, so untouched states keep their bytes.
    assert "gate" not in q.to_dict()["tracks"][0]


def test_set_gate_normalises():
    p = ops.set_gate(base(), "t", [(30, 40), (10, 20), (20, 25), (5, 5)])
    assert p.track("t").gate == ((10, 25), (30, 40))


def test_set_gate_leaves_other_tracks_alone():
    p = ops.set_gate(base(), "t", [(1, 2)])
    assert p.track("u").gate == ()


def test_add_and_remove_gate_range():
    p = ops.add_gate_range(base(), "t", 10, 20)
    p = ops.add_gate_range(p, "t", 15, 30)
    assert p.track("t").gate == ((10, 30),)
    p = ops.remove_gate_range(p, "t", 18, 22)
    assert p.track("t").gate == ((10, 18), (22, 30))


def test_unknown_track_is_the_usual_translated_error():
    for call in (lambda: ops.set_gate(base(), "nope", []),
                 lambda: ops.add_gate_range(base(), "nope", 1, 2),
                 lambda: ops.remove_gate_range(base(), "nope", 1, 2)):
        with pytest.raises(ops.EditError) as err:
            call()
        assert err.value.key == "error.edit.no_track"


def test_gate_ops_are_in_the_edit_vocabulary():
    p = ops.apply(base(), "set_gate", {"track_id": "t", "ranges": [[1, 5]]})
    assert p.track("t").gate == ((1, 5),)
    assert "add_gate_range" in ops.OPS
    assert "remove_gate_range" in ops.OPS


def test_undo_restores_the_previous_gate(tmp_path):
    h = History(tmp_path / "p.kuulas")
    h.commit("track", ops.add_track(h.state, track_id="t", name="A"))
    h.commit("gate 1", ops.set_gate(h.state, "t", [(10, 20)]))
    h.commit("gate 2", ops.set_gate(h.state, "t", [(30, 40)]))
    assert h.state.track("t").gate == ((30, 40),)
    h.undo()
    assert h.state.track("t").gate == ((10, 20),)
    h.undo()
    assert h.state.track("t").gate == ()
    h.redo()
    h.redo()
    assert h.state.track("t").gate == ((30, 40),)
    h.close()


def test_ripple_through_a_gate_shifts_and_trims_it():
    p = ops.set_gate(base(), "t", [(1000, 2000), (5000, 6000), (9000, 9500)])
    q = ops.ripple_delete(p, 1500, 5500)
    # [1000,2000) keeps its head, [5000,6000) keeps its tail and lands on the
    # cut (they touch, so they merge), the last range shifts left by 4000.
    assert q.track("t").gate == ((1000, 2000), (5000, 5500))


def test_ripple_applies_to_every_track_in_scope_only():
    p = ops.set_gate(base(), "t", [(9000, 9500)])
    p = ops.set_gate(p, "u", [(9000, 9500)])
    q = ops.ripple_delete(p, 1000, 2000, track_ids=["t"])
    assert q.track("t").gate == ((8000, 8500),)
    assert q.track("u").gate == ((9000, 9500),)


def test_ripple_through_a_wholly_gated_stretch_removes_it():
    p = ops.set_gate(base(), "t", [(1000, 2000)])
    assert ops.ripple_delete(p, 900, 2100).track("t").gate == ()


# -- Clip.ungated: "the mic stays open under this clip" (owner, 21.10.2026) -------------
# A gate is a track property, but the owner must be able to unset it for any clip or
# several, and the result must follow the clip: a clip that is half silenced and half not
# after a trim is confusing.

def test_a_clip_is_gated_by_default_and_the_flag_is_not_written_when_false():
    p = base()
    clip = p.track("t").clips[0]
    assert clip.ungated is False
    assert "ungated" not in clip.to_dict()


def test_the_flag_round_trips():
    p = ops.set_clips_ungated(base(), ["c"], True)
    q = Project.from_json(p.to_json())
    assert q.track("t").clips[0].ungated is True
    assert q == p


def test_setting_the_flag_opens_the_gate_under_the_clip():
    p = ops.set_gate(base(), "t", [(0, 70 * RATE)])  # the clip covers 0 .. 60 s
    q = ops.set_clips_ungated(p, ["c", "nope"], True)
    assert q.track("t").gate == ((60 * RATE, 70 * RATE),)


def test_clearing_the_flag_leaves_the_gate_as_it_is():
    p = ops.set_clips_ungated(ops.set_gate(base(), "t", [(0, 70 * RATE)]), ["c"], True)
    q = ops.set_clips_ungated(p, ["c"], False)
    assert q.track("t").clips[0].ungated is False
    assert q.track("t").gate == p.track("t").gate


def test_normalize_is_the_identity_when_no_clip_is_flagged():
    p = ops.set_gate(base(), "t", [(10, 20)])
    assert ops.normalize_ungated(p) is p


def test_normalize_opens_what_a_gate_closes_under_a_flagged_clip():
    p = ops.set_clips_ungated(base(), ["c"], True)
    closed = ops.set_gate(p, "t", [(5 * RATE, 9 * RATE), (70 * RATE, 80 * RATE)])
    assert ops.normalize_ungated(closed).track("t").gate == ((70 * RATE, 80 * RATE),)


def test_trimming_a_flagged_clip_outward_is_followed_by_the_open_gate():
    """The screenshot case: un-silence a clip, then drag its left border outward: the new
    part must not fall under the still-closed gate (the commit path normalises)."""
    p = ops.set_gate(base(), "t", [(0, 30 * RATE)])
    p = ops.trim_clip(p, "c", start=10 * RATE)  # the clip now starts at 10 s
    p = ops.set_clips_ungated(p, ["c"], True)
    assert p.track("t").gate == ((0, 10 * RATE),)
    p = ops.trim_clip(p, "c", start=4 * RATE)  # border dragged outward
    assert ops.normalize_ungated(p).track("t").gate == ((0, 4 * RATE),)
