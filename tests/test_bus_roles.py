"""Bus roles: a bus may carry a role (speech / music) that its tracks inherit
as stored data, so the many readers of ``Track.kind`` need no resolver."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from kuulas import automix, ops
from kuulas.model import Bus, Project, Track
from kuulas.session import Session

RATE = 48000


def project():
    p = Project(rate=1000)
    for tid in ("a", "b", "c"):
        p = ops.add_track(p, track_id=tid, name=tid.upper())
    return ops.add_bus(p, bus_id="m", name="Music", track_ids=["a", "b"])


def kinds(p):
    return {t.id: t.kind for t in p.tracks}


def test_bus_role_defaults_to_none_and_round_trips():
    assert Bus(id="x", name="X").kind is None
    bus = Bus(id="x", name="X", kind="music")
    assert Bus.from_dict(bus.to_dict()) == bus
    assert Bus.from_dict({"id": "x", "name": "X"}).kind is None


def test_setting_a_role_sets_every_track_on_the_bus_only():
    p = ops.set_bus(project(), "m", kind="music")
    assert p.bus("m").kind == "music"
    assert kinds(p) == {"a": "music", "b": "music", "c": "speech"}


def test_clearing_the_role_leaves_the_tracks_alone():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_bus(p, "m", kind=None)
    assert p.bus("m").kind is None
    assert kinds(p)["a"] == "music"


def test_bad_role_is_refused():
    with pytest.raises(ops.EditError):
        ops.set_bus(project(), "m", kind="loud")


def test_moving_a_track_to_a_roled_bus_takes_the_role():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_track(p, "c", bus="m")
    assert kinds(p)["c"] == "music"


def test_moving_to_a_bus_without_role_changes_nothing():
    p = ops.set_track(project(), "c", kind="music")
    p = ops.set_track(p, "c", bus="m")
    assert kinds(p)["c"] == "music"
    p = ops.set_track(p, "c", kind="speech")
    assert kinds(p)["c"] == "speech"


def test_manual_override_sticks_and_reapply_fixes_it():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_track(p, "a", kind="speech")
    assert kinds(p)["a"] == "speech"
    p = ops.set_bus(p, "m", kind="music")  # same role again: re-applies
    assert kinds(p)["a"] == "music"


def test_explicit_kind_wins_over_the_bus_role_on_a_move():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_track(p, "c", bus="m", kind="speech")
    assert kinds(p)["c"] == "speech"


def test_role_and_tracks_are_one_undo_step(tmp_path):
    s = Session(tmp_path / "R.kuulas")
    try:
        s.edit("add_track", {"track_id": "a", "name": "A"})
        s.edit("add_bus", {"bus_id": "m", "name": "M", "track_ids": ["a"]})
        s.edit("set_bus", {"bus_id": "m", "kind": "music"})
        assert s.state.tracks[0].kind == "music"
        s.undo()
        assert s.state.tracks[0].kind == "speech"
        assert s.state.bus("m").kind is None
    finally:
        s.close()


def test_two_tracks_moved_onto_a_music_bus_export_as_music(tmp_path):
    s = Session(tmp_path / "Episode.kuulas")
    try:
        src = tmp_path / "src"
        src.mkdir()
        paths = []
        for i, name in enumerate(("One", "Two")):
            rng = np.random.default_rng(i)
            f = src / f"{name}.wav"
            sf.write(f, (rng.standard_normal(RATE * 2) * 0.1).astype(np.float32),
                     RATE, subtype="PCM_16")
            paths.append(str(f))
        s.import_media(paths)
        s.edit("add_bus", {"bus_id": "m", "name": "Music"})
        s.edit("set_bus", {"bus_id": "m", "kind": "music"})
        for t in s.state.tracks:
            s.edit("set_track", {"track_id": t.id, "bus": "m"})
        result = automix.export_stems(s, tmp_path / "stems")
        folder = Path(result["path"])
        listing = json.loads((folder / "tracks.json").read_text("utf-8"))
        assert [t["kind"] for t in listing["tracks"]] == ["music", "music"]
        assert all(t["channels"] == 2 for t in listing["tracks"])
        assert all(Path(t["file"]).stem.endswith(" MUSIC") for t in listing["tracks"])
    finally:
        s.close()


def follows(p):
    return {t.id: t.follow_bus_role for t in p.tracks}


def test_follow_flag_defaults_off_and_is_optional_in_the_file():
    p = project()
    assert not any(follows(p).values())
    t = Track(id="x", name="X")
    assert "follow_bus_role" not in t.to_dict()  # old files keep their bytes
    assert Track.from_dict({"id": "x", "name": "X"}).follow_bus_role is False
    on = Track(id="x", name="X", follow_bus_role=True)
    assert Track.from_dict(on.to_dict()).follow_bus_role is True


def test_setting_a_bus_role_makes_children_follow():
    p = ops.set_bus(project(), "m", kind="music")
    assert follows(p) == {"a": True, "b": True, "c": False}


def test_clearing_the_bus_role_stops_following_but_keeps_kinds():
    p = ops.set_bus(ops.set_bus(project(), "m", kind="music"), "m", kind=None)
    assert follows(p)["a"] is False
    assert kinds(p)["a"] == "music"


def test_manual_kind_is_an_override_that_stops_following():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_track(p, "a", kind="speech")
    assert (kinds(p)["a"], follows(p)["a"]) == ("speech", False)


def test_match_bus_role_sets_follow_and_kind_together():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_track(p, "a", kind="speech")
    p = ops.set_track(p, "a", follow_bus_role=True)
    assert (kinds(p)["a"], follows(p)["a"]) == ("music", True)


def test_match_without_a_bus_role_is_refused():
    with pytest.raises(ops.EditError):
        ops.set_track(project(), "a", follow_bus_role=True)
    with pytest.raises(ops.EditError):
        ops.set_track(project(), "c", follow_bus_role=True)


def test_moving_onto_a_roled_bus_follows_and_off_a_bus_stops():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.set_track(p, "c", bus="m")
    assert (kinds(p)["c"], follows(p)["c"]) == ("music", True)
    p = ops.set_track(p, "c", bus=None)
    assert follows(p)["c"] is False
    assert kinds(p)["c"] == "music"


def test_moving_onto_a_bus_without_role_does_not_follow():
    p = ops.set_track(project(), "c", bus="m")
    assert follows(p)["c"] is False


def test_deleting_a_bus_stops_following():
    p = ops.delete_bus(ops.set_bus(project(), "m", kind="music"), "m")
    assert not any(follows(p).values())


def test_a_new_track_created_on_a_roled_bus_follows_it():
    p = ops.set_bus(project(), "m", kind="music")
    p = ops.add_track(p, track_id="n", name="N", bus="m")
    assert (kinds(p)["n"], follows(p)["n"], p.tracks[-1].bus) == ("music", True, "m")
