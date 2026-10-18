"""Markers, regions and chapters in the edit state (WP19h)."""

import json

import pytest

from kuulas import markers, ops
from kuulas.chapters import format_chapters
from kuulas.model import Marker, Media, Project

RATE = 48000


def base() -> Project:
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m1", name="a.wav", channels=1, frames=20 * RATE))
    p = ops.add_media(p, Media(id="m2", name="b.wav", channels=1, frames=20 * RATE))
    p = ops.add_track(p, track_id="t1", name="A")
    p = ops.add_track(p, track_id="t2", name="B")
    p = ops.add_clip(p, track_id="t1", clip_id="c1", media_id="m1", start=0)
    return ops.add_clip(p, track_id="t2", clip_id="c2", media_id="m2", start=0)


def by_name(p: Project) -> dict[str, Marker]:
    return {m.name: m for m in p.markers}


# -- model -------------------------------------------------------------------


def test_empty_markers_keep_the_old_bytes():
    p = base()
    assert "markers" not in p.to_dict()
    assert Project.from_json(p.to_json()) == p


def test_old_json_without_markers_loads():
    p = Project.from_dict({"rate": RATE})
    assert p.markers == ()


def test_markers_round_trip_and_keep_unknown_keys():
    p = ops.add_marker(base(), "a", "Intro", 100)
    raw = json.loads(p.to_json())
    raw["markers"][0]["colour"] = "red"
    back = Project.from_dict(raw)
    assert back.markers[0].name == "Intro"
    assert json.loads(back.to_json())["markers"][0]["colour"] == "red"
    assert "end" not in json.loads(p.to_json())["markers"][0]


# -- ops ---------------------------------------------------------------------


def test_add_marker_keeps_markers_sorted_by_start():
    p = base()
    p = ops.add_marker(p, "b", "Two", 2 * RATE)
    p = ops.add_marker(p, "a", "One", RATE)
    assert [m.name for m in p.markers] == ["One", "Two"]


def test_add_marker_makes_an_id_when_none_given():
    p = ops.add_marker(base(), None, "X", 5)
    assert p.markers[0].id.startswith("k")


def test_add_region_needs_an_end_after_the_start():
    with pytest.raises(ops.EditError) as e:
        ops.add_marker(base(), "r", "R", 10, end=10, kind="region")
    assert e.value.key == "error.marker.bad_range"
    with pytest.raises(ops.EditError):
        ops.add_marker(base(), "r", "R", 10, kind="region")


def test_a_point_marker_has_no_end():
    with pytest.raises(ops.EditError) as e:
        ops.add_marker(base(), "r", "R", 10, end=20, kind="marker")
    assert e.value.key == "error.marker.bad_range"


def test_bad_kind_and_duplicate_id_and_negative_start():
    p = ops.add_marker(base(), "a", "A", 1)
    for call, key in [
        (lambda: ops.add_marker(p, "z", "Z", 1, kind="flag"), "error.marker.bad_kind"),
        (lambda: ops.add_marker(p, "a", "A", 2), "error.marker.exists"),
        (lambda: ops.add_marker(p, "n", "N", -1), "error.marker.bad_range"),
    ]:
        with pytest.raises(ops.EditError) as e:
            call()
        assert e.value.key == key


def test_rename_move_delete():
    p = ops.add_marker(base(), "a", "A", 1)
    p = ops.rename_marker(p, "a", "  Intro ")
    assert p.markers[0].name == "Intro"
    p = ops.move_marker(p, "a", 99)
    assert p.markers[0].start == 99
    p = ops.delete_marker(p, "a")
    assert p.markers == ()
    with pytest.raises(ops.EditError) as e:
        ops.delete_marker(p, "a")
    assert e.value.key == "error.marker.missing"


def test_moving_a_region_keeps_its_length():
    p = ops.add_marker(base(), "r", "R", 100, end=300, kind="region")
    p = ops.move_marker(p, "r", 1000)
    assert (p.markers[0].start, p.markers[0].end) == (1000, 1200)


def test_set_region_end():
    p = ops.add_marker(base(), "r", "R", 100, end=300, kind="region")
    p = ops.set_region_end(p, "r", 500)
    assert p.markers[0].end == 500
    with pytest.raises(ops.EditError):
        ops.set_region_end(p, "r", 100)
    p = ops.add_marker(p, "m", "M", 5)
    with pytest.raises(ops.EditError) as e:
        ops.set_region_end(p, "m", 50)
    assert e.value.key == "error.marker.not_region"


def test_set_marker_kind():
    p = ops.add_marker(base(), "m", "M", 5)
    p = ops.set_marker_kind(p, "m", "chapter")
    assert p.markers[0].kind == "chapter"
    with pytest.raises(ops.EditError) as e:
        ops.set_marker_kind(p, "m", "region")  # no end to give it
    assert e.value.key == "error.marker.bad_range"
    p = ops.set_marker_kind(p, "m", "region", end=50)
    assert (p.markers[0].kind, p.markers[0].end) == ("region", 50)
    p = ops.set_marker_kind(p, "m", "marker")
    assert p.markers[0].end is None


def test_the_ops_are_in_the_whitelist():
    for name in ("add_marker", "rename_marker", "move_marker", "set_region_end",
                 "delete_marker", "set_marker_kind"):
        assert name in ops.OPS
    p = ops.apply(base(), "add_marker", {"marker_id": "a", "name": "A", "start": 3})
    assert p.markers[0].start == 3


# -- ripple ------------------------------------------------------------------


def rippled() -> Project:
    p = base()
    for mid, start, end, kind in [
        ("before", 1 * RATE, None, "marker"),
        ("inside", 5 * RATE, None, "chapter"),
        ("after", 9 * RATE, None, "chapter"),
        ("at_end", 6 * RATE, None, "marker"),
        ("span", 4 * RATE, 8 * RATE, "region"),
        ("gone", 5 * RATE, 5 * RATE + 10, "region"),
        ("later", 7 * RATE, 9 * RATE, "region"),
    ]:
        p = ops.add_marker(p, mid, mid, start, end=end, kind=kind)
    return ops.ripple_delete(p, 4 * RATE, 6 * RATE)


def test_ripple_moves_points_after_the_cut_and_clamps_inside_ones():
    m = by_name(rippled())
    assert m["before"].start == RATE
    assert m["inside"].start == 4 * RATE  # to the cut start
    assert m["at_end"].start == 4 * RATE
    assert m["after"].start == 7 * RATE


def test_ripple_trims_regions_and_drops_swallowed_ones():
    m = by_name(rippled())
    assert "gone" not in m
    assert (m["span"].start, m["span"].end) == (4 * RATE, 6 * RATE)
    assert (m["later"].start, m["later"].end) == (5 * RATE, 7 * RATE)


def test_a_scoped_ripple_leaves_the_markers_alone():
    p = ops.add_marker(base(), "a", "A", 9 * RATE)
    p = ops.ripple_delete(p, 4 * RATE, 6 * RATE, track_ids=["t1"])
    assert p.markers[0].start == 9 * RATE


def test_cut_range_ripple_moves_markers():
    p = ops.add_marker(base(), "a", "A", 9 * RATE)
    p = ops.cut_range(p, 4 * RATE, 6 * RATE, ["t1", "t2"])
    assert p.markers[0].start == 7 * RATE


def test_chapter_times_follow_a_ripple_cut():
    p = ops.add_marker(base(), "a", "Intro", 0, kind="chapter")
    p = ops.add_marker(p, "b", "Main", 10 * RATE, kind="chapter")
    p = ops.ripple_delete(p, 2 * RATE, 4 * RATE)
    text = format_chapters([(m.start, m.name) for m in p.markers], RATE, "text")
    assert text == "00:00:00 Intro\n00:00:08 Main\n"


# -- insert ripples ----------------------------------------------------------


def test_opening_a_gap_shifts_later_markers_and_stretches_a_straddling_region():
    p = ops.add_marker(base(), "a", "A", 9 * RATE)
    p = ops.add_marker(p, "b", "B", 2 * RATE)
    p = ops.add_marker(p, "r", "R", 1 * RATE, end=5 * RATE, kind="region")
    out = markers.open_gap(p.markers, 3 * RATE, RATE)
    got = {m.name: (m.start, m.end) for m in out}
    assert got["A"] == (10 * RATE, None)
    assert got["B"] == (2 * RATE, None)
    assert got["R"] == (RATE, 6 * RATE)
