import pytest

from kuulas.clipboard import ClipRef, Entry
from kuulas.messages import KuulasError
from kuulas.model import Clip, Media, Project, Track
from kuulas.ops import EditError
from kuulas.paste_plan import PastePlan, plan_paste

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
         length: int = 10_000) -> Clip:
    return Clip(clip_id, media_id, start, offset, length)


def entry(**over) -> Entry:
    base = {"id": "e1", "name": "", "created_utc": 1000.0, "refs": (),
            "span": (0, 0), "source_project": "", "pinned": False}
    base.update(over)
    return Entry(**base)


def test_insert_on_empty_space():
    p = project(track("ta"))  # the target track has nothing on it
    e = entry(span=(1_000, 3_000), refs=(
        ClipRef("a" * 64, 0, 2_000, gain_db=-1.5, pan=0.25, fade_in=480,
                fade_out=960, muted=True, rel_start=0, track_slot=0),))

    got = plan_paste(p, e, 10_000, "insert")

    assert got == PastePlan(
        placements=(
            ("ta", "a" * 64, 10_000, 0, 2_000, -1.5, 0.25, 480, 960, True),),
        shift=2_000, removed=(), missing=())


def test_insert_in_the_middle_shifts_later_material_and_removes_nothing():
    p = project(track(
        "ta",
        # Overlaps the stretch the entry lands on, but insert ripples
        # later material right instead of overwriting anything.
        clip("straddler", start=1_000, length=4_000),
        clip("before", start=0, length=500),
        clip("after", start=9_000, length=1_000),
    ))
    e = entry(span=(100, 2_100), refs=(
        ClipRef("a" * 64, 0, 2_000, rel_start=0, track_slot=0),))

    got = plan_paste(p, e, 2_000, "insert")

    # Later material moves right by the entry's length; nothing is removed.
    assert got.shift == 2_000
    assert got.removed == ()
    assert got.placements == (
        ("ta", "a" * 64, 2_000, 0, 2_000, 0.0, 0.0, 0, 0, False),)


def test_overwrite_removes_exactly_the_covered_stretch():
    p = project(
        track("ta",
              # Ends exactly where the paste starts: touching, not under it.
              clip("touch", start=0, length=1_000),
              # Overlaps the right part of the stretch: under it.
              clip("straddle", start=2_000, length=4_000),
              # Starts exactly where the paste ends: touching, not under it.
              clip("after", start=3_000, length=1_000)),
        track("tb",
              clip("inside", start=1_500, length=500),
              clip("far", start=9_000, length=500)),
        # tc is mapped but the entry uses neither its slot nor it.
        track("tc", clip("under", start=1_000, length=500)),
    )
    # Slots 0 and 1 in the source project's order; slot 2 is never used.
    e = entry(span=(0, 2_000), refs=(
        ClipRef("a" * 64, 0, 2_000, rel_start=0, track_slot=0),
        ClipRef("b" * 64, 0, 900, rel_start=100, track_slot=1),))

    got = plan_paste(p, e, 1_000, "overwrite", {0: "ta", 1: "tb", 2: "tc"})

    # Overwrite stays in place and reports the covered stretch on every
    # target track that has material under it, once, in project order.
    assert got.shift == 0
    assert got.removed == (("ta", 1_000, 3_000), ("tb", 1_000, 3_000))
    assert got.placements == (
        ("ta", "a" * 64, 1_000, 0, 2_000, 0.0, 0.0, 0, 0, False),
        ("tb", "b" * 64, 1_100, 0, 900, 0.0, 0.0, 0, 0, False))


def test_none_keeps_the_relative_layout_across_two_tracks():
    p = project(
        track("tx", clip("x1", start=0, length=1_000)),
        track("ty", clip("y1", "mb", start=2_000, length=1_000)),
        track("tz", clip("z1", "mb", start=0, length=1_000)),
    )
    # Copied from a source whose track order was (sa, sb): slot 0 on sa,
    # slot 1 on sb, with sb's clip 500 frames later than sa's.
    e = entry(span=(0, 2_000), refs=(
        ClipRef("a" * 64, 1_000, 2_000, gain_db=-2.0, rel_start=0,
               track_slot=0),
        ClipRef("b" * 64, 4_000, 1_500, pan=0.5, rel_start=500,
                track_slot=1),))

    got = plan_paste(p, e, 7_000, "insert")

    # No mapping: slot i lands on the i-th track, which for dense slots is
    # both "the same tracks" in the source project and "the first tracks"
    # in any other. Media are found by sha256, not by source track.
    assert got.placements == (
        ("tx", "a" * 64, 7_000, 1_000, 2_000, -2.0, 0.0, 0, 0, False),
        ("ty", "b" * 64, 7_500, 4_000, 1_500, 0.0, 0.5, 0, 0, False))
    assert got.shift == 2_000
    assert got.removed == ()
    assert got.missing == ()


def test_missing_media_is_reported_and_left_out():
    p = project(track("ta"))
    e = entry(span=(0, 2_000), refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=0),
        ClipRef("c" * 64, 0, 500, rel_start=1_000, track_slot=0),
        ClipRef("c" * 64, 5_000, 500, rel_start=1_500, track_slot=0),))

    got = plan_paste(p, e, 0, "insert")

    # Missing media are no error: reported once, sorted, and their clips
    # are not placed. The entry still occupies its whole stretch.
    assert got.missing == ("c" * 64,)
    assert got.placements == (
        ("ta", "a" * 64, 0, 0, 1_000, 0.0, 0.0, 0, 0, False),)
    assert got.shift == 2_000


def test_a_missing_slot_raises_and_unused_slots_are_not_validated():
    p = project(track("ta"), track("tb"))
    e = entry(span=(0, 1_000), refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=1),))

    # The entry uses slot 1; the mapping lacks it.
    with pytest.raises(KuulasError) as err:
        plan_paste(p, e, 0, "insert", {0: "ta"})
    assert err.value.key == "error.paste.missing_slot"

    # A slot the entry does not use is neither validated nor pasted, so
    # the unknown track id on the unused slot 2 raises nothing.
    got = plan_paste(p, e, 0, "insert", {1: "tb", 2: "gone"})
    assert got.placements[0][0] == "tb"


def test_none_raises_when_the_project_has_too_few_tracks():
    p = project(track("ta"))  # one track; the entry uses slots 0 and 1
    e = entry(span=(0, 1_000), refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=0),
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=1),))

    with pytest.raises(KuulasError) as err:
        plan_paste(p, e, 0, "insert")
    assert err.value.key == "error.paste.missing_slot"

    # A malformed negative slot never wraps onto the last track.
    e = entry(span=(0, 1_000), refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=-1),))
    with pytest.raises(KuulasError) as err:
        plan_paste(p, e, 0, "insert")
    assert err.value.key == "error.paste.missing_slot"


def test_an_unknown_track_id_on_a_used_slot_raises():
    p = project(track("ta"))
    e = entry(span=(0, 1_000), refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=0),))

    with pytest.raises(EditError) as err:
        plan_paste(p, e, 0, "insert", {0: "gone"})
    assert err.value.key == "error.edit.no_track"


def test_an_unknown_mode_raises():
    p = project(track("ta"))
    e = entry(span=(0, 1_000), refs=(
        ClipRef("a" * 64, 0, 1_000, rel_start=0, track_slot=0),))

    with pytest.raises(KuulasError) as err:
        plan_paste(p, e, 0, "blend")
    assert err.value.key == "error.paste.unknown_mode"
