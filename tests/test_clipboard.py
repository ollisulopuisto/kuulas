import json

import pytest

from kuulas.clipboard import (
    ClipboardHistory,
    ClipRef,
    Entry,
    adopted_copy,
    from_json,
    make_entry,
    make_entry_range,
    prune_entries,
    to_json,
)
from kuulas.model import Clip, Media, Point, Project, Track
from kuulas.ops import EditError

RATE = 48_000


def media(media_id: str, digest: str) -> Media:
    return Media(media_id, f"{media_id}.wav", 1, 200_000, sha256=digest)


def track(track_id: str, *clips: Clip) -> Track:
    return Track(track_id, track_id, kind="speech", clips=clips)


def project(*tracks: Track) -> Project:
    return Project(
        rate=RATE,
        media=(media("ma", "a" * 64), media("mb", "b" * 64)),
        tracks=tracks,
    )


def clip(clip_id: str, media_id: str = "ma", *, start: int = 0, offset: int = 0,
         length: int = 10_000, gain_db: float = 0.0, pan: float = 0.0,
         fade_in: int = 0, fade_out: int = 0, muted: bool = False,
         envelope: tuple[Point, ...] = ()) -> Clip:
    return Clip(clip_id, media_id, start, offset, length, gain_db=gain_db, pan=pan,
                fade_in=fade_in, fade_out=fade_out, muted=muted, envelope=envelope)


def entry(**over) -> Entry:
    base = {"id": "e1", "name": "", "created_utc": 1000.0, "refs": (),
            "span": (0, 0), "source_project": "", "pinned": False}
    base.update(over)
    return Entry(**base)


def test_a_clip_selection_keeps_relative_layout_and_track_slots():
    p = project(
        track("ta", clip("a1", start=5_000, length=2_000, gain_db=-3.0, pan=0.25,
                         fade_in=480, fade_out=960,
                         envelope=((500, -6.0), (1500, -3.0))),
                  clip("a2", "ma", start=9_000, offset=9_000, length=1_000)),
        # tb comes later in the project and its copied clip starts earlier:
        # slots follow the project's track order, not the timeline.
        track("tb", clip("b1", "mb", start=1_000, length=7_000)),
    )

    # A scrambled selection order must not change the entry.
    got = make_entry(p, ["b1", "a2", "a1"], now=1000.0)

    assert got.id  # a unique, time-ordered hex string
    assert got.name == ""
    assert got.created_utc == 1000.0
    assert got.span == (1_000, 10_000)
    assert got.source_project == ""
    assert got.pinned is False
    assert got.refs == (
        ClipRef("b" * 64, 0, 7_000, track_slot=1, rel_start=0),
        ClipRef("a" * 64, 0, 2_000, gain_db=-3.0, pan=0.25, fade_in=480,
                fade_out=960, envelope=((500, -6.0), (1500, -3.0)),
                track_slot=0, rel_start=4_000),
        ClipRef("a" * 64, 9_000, 1_000, track_slot=0, rel_start=8_000),
    )


def test_two_entries_made_at_the_same_now_have_distinct_ids():
    p = project(track("ta", clip("a1")))
    e1 = make_entry(p, ["a1"], now=1000.0)
    e2 = make_entry(p, ["a1"], now=1000.0)

    assert e1.id != e2.id
    assert e1.id < e2.id  # time-ordered within the process


def test_a_range_copy_trims_correctly_at_both_edges():
    p = project(
        track("ta",
              # Overlaps the range's left edge: its own start is cut away
              # (fade_in lost), its own end is kept (fade_out kept).
              clip("left", "ma", start=0, offset=0, length=2_500,
                   gain_db=-1.5, fade_in=480, fade_out=960,
                   envelope=((500, -6.0), (2000, -2.0))),
              # Fully inside: everything kept as-is.
              clip("mid", "ma", start=3_000, offset=3_000, length=4_000,
                   fade_in=480, fade_out=960),
              # Past the range's right edge: not copied at all.
              clip("right", "ma", start=8_500, offset=8_500, length=1_500)),
        track("tb",
              # Starts before the range and ends inside it: its own start
              # is cut (fade_in lost), its own end kept (fade_out kept).
              clip("wide", "mb", start=500, offset=1_000, length=6_500,
                   fade_in=480, fade_out=960, muted=True)),
    )

    got = make_entry_range(p, 2_000, 8_000, now=1000.0)

    # span is the copied clips' cover (the range's right edge is silent),
    # not the requested range; rel_start 0 sits at span[0].
    assert got.span == (2_000, 7_000)
    assert got.refs == (
        # left: own start cut (fade_in lost), own end kept (fade_out kept,
        # clamped to the trimmed length, as `ops` trims it).
        ClipRef("a" * 64, 2_000, 500, gain_db=-1.5, fade_out=500,
                envelope=((500, -6.0), (2000, -2.0)), track_slot=0,
                rel_start=0),
        # wide: own start cut (fade_in lost), own end kept (fade_out kept),
        # offset moved by the left trim, muted kept.
        ClipRef("b" * 64, 2_500, 5_000, fade_out=960, muted=True,
                track_slot=1, rel_start=0),
        ClipRef("a" * 64, 3_000, 4_000, fade_in=480, fade_out=960,
                track_slot=0, rel_start=1_000),
    )


def test_a_kept_fade_is_clamped_to_the_trimmed_length():
    p = project(
        track("ta",
              # The kept part is shorter than the clip's own fade.
              clip("c", "ma", start=0, offset=0, length=1_000, fade_in=960)),
    )

    got = make_entry_range(p, 0, 500, now=1000.0)

    # Own start kept (fade_in kept but clamped to the trimmed length, as
    # `ops` trims it), own end trimmed (fade_out lost).
    assert got.refs == (
        ClipRef("a" * 64, 0, 500, fade_in=500, track_slot=0, rel_start=0),
    )


def test_track_ids_choose_the_tracks():
    p = project(
        track("ta", clip("a1", start=1_000, length=2_000)),
        track("tb", clip("b1", "mb", start=1_000, length=2_000)),
    )

    got = make_entry_range(p, 0, 4_000, ["tb"], now=1000.0)

    # The only touched track is slot 0, whichever it is in the project.
    assert got.refs == (ClipRef("b" * 64, 0, 2_000, track_slot=0, rel_start=0),)


def test_pin_protects_from_pruning():
    h = ClipboardHistory(max_entries=3)
    for i in range(4):  # e0 .. e3, oldest first
        h.add(entry(id=f"e{i}", created_utc=1000.0 + i))

    # Beyond the max the oldest unpinned entry is dropped; the rest stay
    # newest first.
    assert [e.id for e in h.entries()] == ["e3", "e2", "e1"]
    assert h.get("e0") is None

    # Pin the oldest survivor: the next add drops the next-oldest unpinned
    # entry instead, never the pinned one.
    h.pin("e1")
    h.add(entry(id="e9", created_utc=1009.0))

    # The limit counts unpinned entries only (WP46): e1 is pinned, so three
    # unpinned ones (e9, e3, e2) still fit beside it.
    assert [e.id for e in h.entries()] == ["e9", "e3", "e2", "e1"]
    h.add(entry(id="e8", created_utc=1008.0))
    assert [e.id for e in h.entries()] == ["e8", "e9", "e3", "e1"]

    # Pinned entries are never dropped, so a history may exceed its max.
    h.pin("e3")
    h.pin("e9")
    h.add(entry(id="e10", created_utc=1010.0))

    assert [e.id for e in h.entries()] == ["e10", "e8", "e9", "e3", "e1"]


def test_prune_entries_keeps_every_pinned_and_the_newest_unpinned():
    items = [entry(id=f"e{i}", pinned=i in (1, 4)) for i in range(6)]  # newest first
    kept = prune_entries(items, 2)
    # unpinned: e0 e2 kept (2 newest), e3 e5 dropped; pinned e1 e4 stay in place
    assert [e.id for e in kept] == ["e0", "e1", "e2", "e4"]
    assert prune_entries(items, 0) == [items[0], items[1], items[4]]  # newest survives
    assert prune_entries([], 5) == []


def test_unpinning_prunes_past_the_limit():
    h = ClipboardHistory(max_entries=1)
    h.add(entry(id="a"))
    h.pin("a")
    h.add(entry(id="b"))
    h.unpin("a")
    assert [e.id for e in h.entries()] == ["b"]


def test_pin_unpin_rename_delete():
    h = ClipboardHistory(max_entries=5)
    h.add(entry(id="e1"))
    h.add(entry(id="e2"))

    h.rename("e1", "Interview bit")
    assert h.get("e1") == entry(id="e1", name="Interview bit")

    h.unpin("e2")  # no-op on an unpinned entry
    assert h.get("e2").pinned is False

    h.pin("e2")
    assert h.get("e2").pinned is True

    h.delete("e1")
    assert h.get("e1") is None
    assert [e.id for e in h.entries()] == ["e2"]
    assert h.entries()[0].pinned is True  # the pin survived the rename copy

    with pytest.raises(KeyError):
        h.delete("gone")
    with pytest.raises(KeyError):
        h.pin("gone")
    with pytest.raises(KeyError):
        h.unpin("gone")
    with pytest.raises(KeyError):
        h.rename("gone", "x")


def test_entry_and_history_round_trips():
    e = entry(id="e1", name="bit", created_utc=1000.5, span=(1_000, 7_000),
              source_project="/x/y.kuulas", pinned=True, refs=(
                  ClipRef("a" * 64, 3_000, 4_000, gain_db=-1.25, pan=0.5,
                          fade_in=480, fade_out=960, muted=True,
                          envelope=((3_100, -6.0), (5_000, -2.5)),
                          rel_start=1_000, track_slot=1),
                  ClipRef("b" * 64, 0, 1_000, rel_start=0, track_slot=0),
              ))

    text = to_json(e)

    assert from_json(text) == e
    assert to_json(from_json(text)) == text

    h = ClipboardHistory(max_entries=7)
    h.add(entry(id="e0", created_utc=999.0))
    h.add(e)

    assert ClipboardHistory.from_json(h.to_json()).entries() == h.entries()
    assert ClipboardHistory.from_json(h.to_json()).max_entries == 7


def test_unknown_keys_survive_a_round_trip():
    e = entry(id="e1", created_utc=1000.0, refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=0),))
    d = json.loads(to_json(e))
    d["mood"] = "future"  # an entry-level key this version does not model
    d["refs"][0]["speed"] = 1.25  # a ref-level key

    out = json.loads(to_json(from_json(json.dumps(d))))

    assert out["mood"] == "future"
    assert out["refs"][0]["speed"] == 1.25
    # The rest of the entry is intact after carrying the unknown keys.
    assert from_json(json.dumps(out)) == from_json(json.dumps(d))


def test_an_empty_selection_raises_and_stale_ids_raise_their_own_keys():
    p = project(track("ta", clip("a1", start=1_000, length=2_000)))

    with pytest.raises(EditError) as err:
        make_entry(p, [], now=1000.0)
    assert err.value.key == "error.edit.no_selection"

    # A range that catches no clip (an empty or reversed one catches none).
    with pytest.raises(EditError) as err:
        make_entry_range(p, 4_000, 9_000, now=1000.0)
    assert err.value.key == "error.edit.no_selection"

    with pytest.raises(EditError) as err:
        make_entry_range(p, 0, 0, now=1000.0)
    assert err.value.key == "error.edit.no_selection"

    with pytest.raises(EditError) as err:
        make_entry(p, ["gone"], now=1000.0)
    assert err.value.key == "error.edit.no_clip"

    with pytest.raises(EditError) as err:
        make_entry_range(p, 0, 2_000, ["gone"], now=1000.0)
    assert err.value.key == "error.edit.no_track"


def test_an_entry_remembers_its_source_track_names_by_slot():
    p = project(
        track("ta", clip("a1", start=5_000, length=2_000)),
        track("tb", clip("b1", "mb", start=1_000, length=7_000)),
        track("tc", clip("c1", start=0, length=100)),
    )
    got = make_entry(p, ["b1", "a1"], now=1000.0)  # not tc
    # Slot order is the project's track order; track() names a track by its id.
    assert got.tracks == ("ta", "tb")
    assert from_json(to_json(got)).tracks == ("ta", "tb")
    ranged = make_entry_range(p, 0, 50, ["tc"], now=1000.0)
    assert ranged.tracks == ("tc",)


def history_of(*ids):
    h = ClipboardHistory()
    for n, entry_id in enumerate(reversed(ids)):  # the last added is the first listed
        h.add(entry(id=entry_id, created_utc=1000.0 + n))
    return h


def listed(h):
    return [e.id for e in h.entries()]


def test_move_puts_an_entry_before_another():
    h = history_of("a", "b", "c", "d")
    h.move("d", before="b")
    assert listed(h) == ["a", "d", "b", "c"]


def test_move_to_the_front_and_to_the_end():
    h = history_of("a", "b", "c")
    h.move("c", before="a")
    assert listed(h) == ["c", "a", "b"]
    h.move("c", before=None)
    assert listed(h) == ["a", "b", "c"]


def test_moving_before_itself_or_to_where_it_is_changes_nothing():
    h = history_of("a", "b", "c")
    h.move("b", before="b")
    h.move("b", before="c")
    assert listed(h) == ["a", "b", "c"]


def test_move_names_an_unknown_entry():
    h = history_of("a", "b")
    with pytest.raises(KeyError):
        h.move("zzz", before="a")
    with pytest.raises(KeyError):
        h.move("a", before="zzz")


def test_the_order_survives_a_save_and_a_load_and_a_new_copy_still_goes_first():
    h = history_of("a", "b", "c")
    h.move("c", before="a")
    again = ClipboardHistory.from_json(h.to_json())
    assert listed(again) == ["c", "a", "b"]
    again.add(entry(id="new", created_utc=5000.0))
    assert listed(again) == ["new", "c", "a", "b"]


# -- cart slots (owner, 2026-10-23): numbers 1-9 on up to nine entries -----------------


def test_an_entry_has_no_cart_slot_until_given_one():
    assert entry().cart is None


def test_a_slot_is_given_and_a_number_is_held_by_one_entry_only():
    h = history_of("a", "b", "c")
    h.set_cart("b", 3)
    assert {e.id: e.cart for e in h.entries()} == {"a": None, "b": 3, "c": None}
    h.set_cart("c", 3)  # the number moves: b loses it
    assert {e.id: e.cart for e in h.entries()} == {"a": None, "b": None, "c": 3}


def test_a_slot_can_be_cleared_and_only_one_to_nine_exist():
    h = history_of("a")
    h.set_cart("a", 9)
    h.set_cart("a", None)
    assert h.get("a").cart is None
    for bad in (0, 10, -1, 2.5, "3"):
        with pytest.raises(ValueError, match="slot"):
            h.set_cart("a", bad)
    with pytest.raises(KeyError):
        h.set_cart("zzz", 1)


def test_a_slot_survives_a_save_and_a_load_and_an_old_file_has_none():
    h = history_of("a", "b")
    h.set_cart("a", 2)
    again = ClipboardHistory.from_json(h.to_json())
    assert {e.id: e.cart for e in again.entries()} == {"a": 2, "b": None}
    old = ClipboardHistory.from_json(
        '{"entries":[{"id":"x","name":"","created_utc":1.0,"refs":[],"span":[0,0]}]}')
    assert old.get("x").cart is None


def test_an_adopted_copy_does_not_take_the_slot_of_the_original():
    assert adopted_copy(entry(cart=4)).cart is None
