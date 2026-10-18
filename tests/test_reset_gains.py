"""Reset every track and bus gain to 0 dB (owner, 2026-10-19: unity before export)."""

import pytest

from kuulas import ops
from kuulas.model import Media, Project
from kuulas.session import Session

RATE = 48000


def project() -> Project:
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=10 * RATE))
    p = ops.add_track(p, track_id="A", name="A")
    p = ops.add_track(p, track_id="B", name="B")
    p = ops.add_bus(p, bus_id="X", name="X")
    p = ops.add_clip(p, "A", "m", clip_id="ca")
    p = ops.set_clip(p, "ca", gain_db=3.0)
    p = ops.set_track(p, "A", gain_db=-4.5, pan=0.5)
    p = ops.set_bus(p, "X", gain_db=2.0, pan=-0.25)
    p = ops.set_master(p, -1.5)
    return ops.set_track(p, "B", gain_db=0.0)


def test_registered_as_an_edit():
    assert "reset_gains" in ops.OPS


def test_every_track_and_bus_gain_goes_to_zero():
    p = ops.reset_gains(project())
    assert [t.gain_db for t in p.tracks] == [0.0, 0.0]
    assert [b.gain_db for b in p.buses] == [0.0]


def test_master_clip_gains_and_pan_are_left_alone():
    before = project()
    p = ops.reset_gains(before)
    assert p.master_gain_db == -1.5
    assert p.tracks[0].clips[0].gain_db == 3.0
    assert p.tracks[0].pan == 0.5
    assert p.buses[0].pan == -0.25


def test_a_track_already_at_zero_is_the_same_object():
    before = project()
    p = ops.reset_gains(before)
    assert p.tracks[1] is before.tracks[1]


def test_all_zero_is_an_error_so_the_menu_can_say_so():
    p = ops.reset_gains(project())
    with pytest.raises(ops.EditError) as e:
        ops.reset_gains(p)
    assert e.value.key == "error.edit.no_gains_to_reset"


def test_reset_is_one_undo_step(tmp_path):
    session = Session(tmp_path / "R.kuulas")
    try:
        session.edit("add_track", {"track_id": "A", "name": "A"})
        session.edit("add_bus", {"bus_id": "X", "name": "X"})
        session.edit("set_track", {"track_id": "A", "gain_db": -4.5})
        session.edit("set_bus", {"bus_id": "X", "gain_db": 2.0})
        session.edit("reset_gains", {})
        assert session.state.tracks[0].gain_db == 0.0
        assert session.state.buses[0].gain_db == 0.0
        session.undo()
        assert session.state.tracks[0].gain_db == -4.5
        assert session.state.buses[0].gain_db == 2.0
    finally:
        session.close()
