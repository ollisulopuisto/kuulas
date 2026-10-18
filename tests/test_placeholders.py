"""Narration placeholders in the edit state (WP43): model, ops, ripple, replace."""

import json

import pytest

from kuulas import narration, ops, placeholders
from kuulas.model import Media, Placeholder, Project

RATE = 48000
TEXT = "one two three four five six seven eight nine ten eleven twelve"  # 12 words


def base() -> Project:
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m1", name="a.wav", channels=1, frames=60 * RATE))
    p = ops.add_media(p, Media(id="m2", name="b.wav", channels=1, frames=60 * RATE))
    p = ops.add_media(p, Media(id="take", name="take.wav", channels=1, frames=9 * RATE))
    p = ops.add_track(p, track_id="t1", name="A")
    p = ops.add_track(p, track_id="t2", name="B")
    p = ops.add_clip(p, track_id="t1", clip_id="c1", media_id="m1", start=0,
                     length=30 * RATE)
    return ops.add_clip(p, track_id="t2", clip_id="c2", media_id="m2", start=0,
                        length=30 * RATE)


def one(p: Project) -> Placeholder:
    return p.placeholders[0]


# -- model -------------------------------------------------------------------


def test_no_placeholders_keeps_the_old_bytes():
    p = base()
    assert "placeholders" not in p.to_dict()
    assert Project.from_json(p.to_json()) == p
    assert Project.from_dict({"rate": RATE}).placeholders == ()


def test_round_trip_keeps_unknown_keys():
    p = ops.add_placeholder(base(), "t1", RATE, TEXT, placeholder_id="h1")
    raw = json.loads(p.to_json())
    raw["placeholders"][0]["voice"] = "anna"
    back = Project.from_dict(raw)
    assert back.placeholders[0].text == TEXT
    assert json.loads(back.to_json())["placeholders"][0]["voice"] == "anna"


# -- add / edit --------------------------------------------------------------


def test_add_estimates_the_length():
    p = ops.add_placeholder(base(), "t1", 2 * RATE, TEXT)
    h = one(p)
    assert h.length == narration.estimate_frames(TEXT, RATE)
    assert h.estimated is True
    assert (h.track, h.start, h.text) == ("t1", 2 * RATE, TEXT)


def test_add_with_a_length_is_not_an_estimate():
    h = one(ops.add_placeholder(base(), "t1", 0, TEXT, length=3 * RATE))
    assert (h.length, h.estimated) == (3 * RATE, False)


def test_add_refuses_blank_text_unknown_track_and_duplicate_id():
    p = base()
    with pytest.raises(ops.EditError) as e:
        ops.add_placeholder(p, "t1", 0, "   ")
    assert e.value.key == "error.placeholder.empty_text"
    with pytest.raises(ops.EditError) as e:
        ops.add_placeholder(p, "t1", 0, "... !")  # punctuation only: no words
    assert e.value.key == "error.placeholder.empty_text"
    with pytest.raises(ops.EditError):
        ops.add_placeholder(p, "nope", 0, TEXT)
    p = ops.add_placeholder(p, "t1", 0, TEXT, placeholder_id="h1")
    with pytest.raises(ops.EditError) as e:
        ops.add_placeholder(p, "t1", 0, TEXT, placeholder_id="h1")
    assert e.value.key == "error.placeholder.exists"


def test_edit_text_re_estimates_while_estimated():
    p = ops.add_placeholder(base(), "t1", 0, TEXT, placeholder_id="h1")
    p = ops.edit_placeholder_text(p, "h1", "short line here")
    assert one(p).length == narration.estimate_frames("short line here", RATE)
    assert one(p).estimated is True


def test_a_manual_length_turns_the_estimate_off_and_text_edits_keep_it():
    p = ops.add_placeholder(base(), "t1", 0, TEXT, placeholder_id="h1")
    p = ops.set_placeholder_length(p, "h1", 7 * RATE)
    assert (one(p).length, one(p).estimated) == (7 * RATE, False)
    p = ops.edit_placeholder_text(p, "h1", "changed words")
    assert one(p).length == 7 * RATE
    assert one(p).text == "changed words"


def test_bad_length_and_missing_id():
    p = ops.add_placeholder(base(), "t1", 0, TEXT, placeholder_id="h1")
    with pytest.raises(ops.EditError) as e:
        ops.set_placeholder_length(p, "h1", 0)
    assert e.value.key == "error.placeholder.bad_length"
    with pytest.raises(ops.EditError) as e:
        ops.delete_placeholder(p, "zzz")
    assert e.value.key == "error.placeholder.missing"


def test_move_and_delete_and_order():
    p = ops.add_placeholder(base(), "t1", 5 * RATE, "b b", placeholder_id="hb")
    p = ops.add_placeholder(p, "t2", 2 * RATE, "a a", placeholder_id="ha")
    assert [h.id for h in p.placeholders] == ["ha", "hb"]
    p = ops.move_placeholder(p, "ha", 9 * RATE, track_id="t1")
    assert [h.id for h in p.placeholders] == ["hb", "ha"]
    assert p.placeholders[1].track == "t1"
    p = ops.delete_placeholder(p, "hb")
    assert [h.id for h in p.placeholders] == ["ha"]


def test_delete_track_removes_its_placeholders():
    p = ops.add_placeholder(base(), "t1", 0, TEXT)
    assert ops.delete_track(p, "t1").placeholders == ()


def test_ops_are_reachable_by_name():
    p = ops.apply(base(), "add_placeholder",
                  {"track_id": "t1", "start": 0, "text": TEXT, "placeholder_id": "h1"})
    assert one(p).id == "h1"


# -- ripple ------------------------------------------------------------------


def with_ph(start=10 * RATE, length=4 * RATE, track="t1") -> Project:
    return ops.add_placeholder(base(), track, start, TEXT, length=length,
                               placeholder_id="h1")


def test_ripple_delete_before_shifts_it():
    p = ops.ripple_delete(with_ph(), 2 * RATE, 5 * RATE)
    assert one(p).start == 7 * RATE
    assert one(p).length == 4 * RATE


def test_ripple_delete_after_leaves_it():
    p = ops.ripple_delete(with_ph(), 20 * RATE, 25 * RATE)
    assert one(p).start == 10 * RATE


def test_ripple_delete_inside_trims_and_clears_the_estimate():
    p = ops.ripple_delete(with_ph(), 11 * RATE, 13 * RATE)
    assert (one(p).start, one(p).length, one(p).estimated) == (10 * RATE, 2 * RATE, False)


def test_ripple_delete_covering_removes_it():
    assert ops.ripple_delete(with_ph(), 9 * RATE, 15 * RATE).placeholders == ()


def test_ripple_only_moves_placeholders_on_the_cut_tracks():
    p = ops.ripple_delete(with_ph(), 2 * RATE, 5 * RATE, ["t2"])
    assert one(p).start == 10 * RATE
    p = ops.ripple_delete(with_ph(), 2 * RATE, 5 * RATE, ["t1"])
    assert one(p).start == 7 * RATE


def test_open_gap_moves_later_ones_and_stretches_a_straddler():
    phs = (Placeholder("a", "t1", 10, 5, "x"), Placeholder("b", "t1", 2, 20, "x"),
           Placeholder("c", "t2", 30, 5, "x"))
    out = {h.id: h for h in placeholders.open_gap(phs, {"t1"}, 8, 100)}
    assert out["a"].start == 110
    assert (out["b"].start, out["b"].length) == (2, 120)
    assert out["c"].start == 30


# -- replace with a take -----------------------------------------------------


def test_replace_with_a_longer_take_pushes_later_material_by_the_difference():
    p = with_ph(start=10 * RATE, length=4 * RATE)  # take is 9 s: +5 s
    p = ops.add_clip(p, track_id="t1", clip_id="c3", media_id="m2", start=20 * RATE,
                     length=5 * RATE)
    p = ops.add_placeholder(p, "t1", 40 * RATE, "later", length=RATE, placeholder_id="h2")
    out = ops.replace_placeholder(p, "h1", "take")
    clips = {c.id: c for t in out.tracks for c in t.clips}
    taken = next(c for c in clips.values() if c.media == "take")
    assert (taken.start, taken.length, taken.offset) == (10 * RATE, 9 * RATE, 0)
    assert clips["c3"].start == 25 * RATE
    assert [h.id for h in out.placeholders] == ["h2"]
    assert out.placeholders[0].start == 45 * RATE


def test_replace_with_a_shorter_take_pulls_later_material_back():
    p = with_ph(start=10 * RATE, length=14 * RATE)  # take 9 s: -5 s
    p = ops.add_clip(p, track_id="t1", clip_id="c3", media_id="m2", start=30 * RATE,
                     length=5 * RATE)
    out = ops.replace_placeholder(p, "h1", "take")
    assert {c.id: c for c in out.tracks[0].clips}["c3"].start == 25 * RATE


def test_replace_uses_the_offset():
    out = ops.replace_placeholder(with_ph(), "h1", "take", offset=2 * RATE)
    taken = next(c for t in out.tracks for c in t.clips if c.media == "take")
    assert (taken.offset, taken.length) == (2 * RATE, 7 * RATE)


def test_replace_ripples_the_other_tracks_only_with_group_editing():
    p = with_ph(start=10 * RATE, length=4 * RATE)
    group = ops.mark_in_sync(p, ["c1", "c2"], main="c1")
    out = ops.replace_placeholder(group, "h1", "take", group_editing=True)
    # c2 spans the stretch; its tail moved right by 5 s, so a split happened.
    assert sum(c.length for c in out.tracks[1].clips) == 30 * RATE
    assert max(c.end for c in out.tracks[1].clips) == 35 * RATE
    alone = ops.replace_placeholder(group, "h1", "take", group_editing=False)
    assert max(c.end for c in alone.tracks[1].clips) == 30 * RATE


def test_replace_refuses_unknown_media_and_placeholder():
    with pytest.raises(ops.EditError) as e:
        ops.replace_placeholder(with_ph(), "h1", "nope")
    assert e.value.key == "error.edit.no_media"
    with pytest.raises(ops.EditError):
        ops.replace_placeholder(with_ph(), "zz", "take")
