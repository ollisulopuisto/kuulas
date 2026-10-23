"""The Material list: every recording of the project and how much of it the edit plays
(docs/design/MATERIAL.md)."""

import json

from kuulas import material
from kuulas.model import Clip, Media, Project, Track

RATE = 48_000


def fr(seconds):
    return round(seconds * RATE)


def project(clips, media=None, tracks=None):
    items = media or (
        Media("a", "Anna.wav", 1, fr(10), sha256="a" * 64),
        Media("b", "Ville.wav", 1, fr(20), sha256="b" * 64),
        Media("c", "Spare take.wav", 1, fr(5), sha256="c" * 64),
    )
    return Project(rate=RATE, media=tuple(items),
                   tracks=tracks or (Track("t", "Voice", clips=tuple(clips)),))


def row(rows, media_id):
    return next(r for r in rows if r["id"] == media_id)


def test_a_recording_played_whole_is_all_used():
    p = project([Clip("c1", "a", 0, 0, fr(10))])
    r = row(material.rows(p), "a")
    assert (r["used_s"], r["cut_s"], r["unused_s"]) == (10.0, 0.0, 0.0)
    assert r["state"] == "used"
    assert r["seconds"] == 10.0


def test_a_recording_played_in_part_says_how_much():
    p = project([Clip("c1", "b", 0, fr(5), fr(8))])
    r = row(material.rows(p), "b")
    assert (r["used_s"], r["unused_s"]) == (8.0, 12.0)
    assert r["state"] == "partly"


def test_a_recording_only_muted_is_cut():
    p = project([Clip("c1", "a", 0, 0, fr(10), muted=True)])
    r = row(material.rows(p), "a")
    assert (r["used_s"], r["cut_s"]) == (0.0, 10.0)
    assert r["state"] == "cut"


def test_a_recording_nowhere_on_the_timeline_is_unused():
    p = project([Clip("c1", "a", 0, 0, fr(10))])
    r = row(material.rows(p), "c")
    assert r["state"] == "unused"
    assert (r["used_s"], r["cut_s"], r["unused_s"]) == (0.0, 0.0, 5.0)


def test_a_missing_file_is_marked():
    p = project([Clip("c1", "a", 0, 0, fr(10))])
    assert row(material.rows(p, missing={"a"}), "a")["missing"] is True
    assert row(material.rows(p, missing={"a"}), "b")["missing"] is False


def test_recorded_takes_are_marked_by_where_the_file_lives():
    p = project([])
    rows = material.rows(p, recorded={"c"})
    assert row(rows, "c")["recorded"] is True
    assert row(rows, "a")["recorded"] is False


def test_newest_first_and_excerpts_are_left_out():
    media = (
        Media("a", "A.wav", 1, fr(10), sha256="a" * 64),
        Media("x", "A excerpt.wav", 1, fr(2), sha256="x" * 64, excerpt_of="a"),
        Media("b", "B.wav", 1, fr(10), sha256="b" * 64),
    )
    p = project([], media=media)
    assert [r["id"] for r in material.rows(p)] == ["b", "a"]


def test_the_rows_are_plain_json():
    p = project([Clip("c1", "a", 0, 0, fr(10))])
    rows = material.rows(p)
    assert json.loads(json.dumps(rows)) == rows
