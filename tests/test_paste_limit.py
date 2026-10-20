"""Paste limited to the marked In..Out range, and overwrite as the paste default.

Plan level (``plan_paste``) and ops level (``apply_paste``): what is under the pasted
clip is trimmed, split or removed, nothing later moves, and the media are never touched
(ground rule 17).
"""

from kuulas.clipboard import ClipRef, Entry
from kuulas.model import Clip, Media, Project, Track
from kuulas.paste_apply import apply_paste
from kuulas.paste_plan import plan_paste

RATE = 48_000
A = "a" * 64
B = "b" * 64


def project(*clips: Clip, tracks: int = 1) -> Project:
    made = [Track("ta", "ta", kind="speech", clips=clips)]
    made += [Track(f"t{i}", f"t{i}", kind="speech") for i in range(1, tracks)]
    return Project(
        rate=RATE,
        media=(Media("ma", "ma.wav", 1, 400_000, sha256=A),
               Media("mb", "mb.wav", 1, 400_000, sha256=B)),
        tracks=tuple(made),
    )


def entry(span: int, *refs: ClipRef) -> Entry:
    return Entry(id="e1", name="", created_utc=1.0, span=(0, span), refs=refs,
                 source_project="", pinned=False)


def one(length: int, *, offset: int = 0, **kw) -> Entry:
    return entry(length, ClipRef(A, offset, length, rel_start=0, track_slot=0, **kw))


def paste(p, e, at, mode="overwrite", out=None):
    plan = plan_paste(p, e, at, mode, None, out=out)
    return apply_paste(p, e, plan, at, {t.id for t in p.tracks[:1]}, mode, out=out)


def spans(p, index=0):
    return sorted((c.start, c.end, c.offset, c.length) for c in p.tracks[index].clips)


# --- plan: In..Out limit ------------------------------------------------------

def test_out_trims_the_pasted_clip_as_a_window_not_the_media():
    got = plan_paste(project(), one(5_000, offset=100, fade_in=200, fade_out=300),
                     1_000, "overwrite", out=3_000)
    # Starts at In, ends at Out; the offset stays, the tail is cut, so the fade-out
    # of the original end no longer applies.
    assert got.placements == (("ta", A, 1_000, 100, 2_000, 0.0, 0.0, 200, 0, False),)


def test_a_shorter_clip_keeps_its_length_and_is_not_stretched():
    got = plan_paste(project(), one(1_000, fade_out=300), 1_000, "overwrite", out=9_000)
    assert got.placements == (("ta", A, 1_000, 0, 1_000, 0.0, 0.0, 0, 300, False),)


def test_multi_clip_keeps_layout_and_trims_every_clip_to_out():
    e = entry(4_000,
              ClipRef(A, 0, 4_000, rel_start=0, track_slot=0),
              ClipRef(B, 50, 1_000, rel_start=1_500, track_slot=1),
              ClipRef(B, 0, 1_000, rel_start=3_000, track_slot=1))
    got = plan_paste(project(tracks=2), e, 1_000, "overwrite", out=3_000)
    # The third clip would start at 4000, past Out: left out entirely.
    assert got.placements == (
        ("ta", A, 1_000, 0, 2_000, 0.0, 0.0, 0, 0, False),
        ("t1", B, 2_500, 50, 500, 0.0, 0.0, 0, 0, False))


def test_overwrite_with_out_replaces_only_in_to_out():
    p = project(Clip("x", "ma", 0, 0, 20_000))
    assert plan_paste(p, one(5_000), 1_000, "overwrite", out=3_000).removed == (
        ("ta", 1_000, 3_000),)
    assert plan_paste(p, one(500), 1_000, "overwrite", out=3_000).removed == (
        ("ta", 1_000, 1_500),)


def test_insert_with_out_shifts_by_the_limited_length():
    p = project()
    assert plan_paste(p, one(5_000), 1_000, "insert", out=3_000).shift == 2_000
    assert plan_paste(p, one(5_000), 1_000, "insert").shift == 5_000
    assert plan_paste(p, one(5_000), 1_000, "insert", out=99_000).shift == 5_000


def test_an_empty_range_places_nothing():
    got = plan_paste(project(Clip("x", "ma", 0, 0, 5_000)), one(1_000), 1_000,
                     "overwrite", out=1_000)
    assert got.placements == ()
    assert got.removed == ()


# --- ops: overwrite under a paste ---------------------------------------------

def test_overwrite_splits_a_clip_under_it_and_moves_nothing():
    p = project(Clip("x", "ma", 0, 0, 10_000), Clip("y", "ma", 12_000, 0, 1_000))
    got = paste(p, one(2_000, offset=50_000), 3_000)
    assert spans(got) == [
        (0, 3_000, 0, 3_000),
        (3_000, 5_000, 50_000, 2_000),
        (5_000, 10_000, 5_000, 5_000),
        (12_000, 13_000, 0, 1_000),
    ]


def test_overwrite_trims_edges_and_removes_covered_clips():
    p = project(Clip("l", "ma", 0, 0, 3_000), Clip("m", "ma", 3_000, 0, 1_000),
                Clip("r", "ma", 4_000, 0, 6_000))
    got = paste(p, one(3_000, offset=9_000), 2_000)
    assert spans(got) == [
        (0, 2_000, 0, 2_000),
        (2_000, 5_000, 9_000, 3_000),
        (5_000, 10_000, 1_000, 5_000),
    ]


def test_insert_still_moves_later_material():
    p = project(Clip("x", "ma", 0, 0, 1_000), Clip("y", "ma", 5_000, 0, 1_000))
    assert (7_000, 8_000, 0, 1_000) in spans(paste(p, one(2_000), 2_000, mode="insert"))


def test_in_out_window_overwrites_only_that_stretch_and_leaves_media_alone():
    p = project(Clip("x", "ma", 0, 0, 20_000))
    got = paste(p, one(9_000, offset=100_000), 4_000, out=6_000)
    assert spans(got) == [
        (0, 4_000, 0, 4_000),
        (4_000, 6_000, 100_000, 2_000),
        (6_000, 20_000, 6_000, 14_000),
    ]
    assert got.media == p.media  # recorded material untouched
