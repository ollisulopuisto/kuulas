"""The play-preview of a clipboard entry (WP46): a temporary project, nothing played."""

from kuulas.clipboard import ClipRef, Entry
from kuulas.clipboard_preview import preview_project
from kuulas.model import Clip, Media, Project, Track

RATE = 48_000


def entry(*refs, span=(5_000, 9_000)):
    return Entry("e1", "", 1000.0, refs=refs, span=span)


def project():
    return Project(
        rate=RATE,
        media=(Media("ma", "a.wav", 1, 200_000, sha256="a" * 64),),
        tracks=(
            Track("t1", "One", kind="speech", clips=(Clip("c1", "ma", 0, 0, 50_000),)),
            Track("t2", "Two", kind="speech", clips=(Clip("c2", "ma", 0, 0, 50_000),)),
        ),
    )


def test_the_preview_holds_only_the_entry_from_frame_zero_on_its_tracks():
    p = project()
    e = entry(
        ClipRef("a" * 64, 10, 1_000, rel_start=0, track_slot=0),
        ClipRef("a" * 64, 500, 2_000, gain_db=-3.0, rel_start=2_000, track_slot=1),
    )
    got, missing = preview_project(p, e)
    assert missing == ()
    assert [(t.id, [(c.start, c.offset, c.length, c.gain_db) for c in t.clips])
            for t in got.tracks] == [
        ("t1", [(0, 10, 1_000, 0.0)]),
        ("t2", [(2_000, 500, 2_000, -3.0)]),
    ]
    assert got.rate == p.rate
    assert got.media == p.media


def test_the_real_project_is_untouched():
    p = project()
    preview_project(p, entry(ClipRef("a" * 64, 0, 1_000)))
    assert [len(t.clips) for t in p.tracks] == [1, 1]


def test_media_the_project_lacks_is_reported_and_left_out():
    e = entry(ClipRef("f" * 64, 0, 1_000),
              ClipRef("a" * 64, 0, 500, rel_start=1_000))
    got, missing = preview_project(project(), e)
    assert missing == ("f" * 64,)
    assert [c.length for t in got.tracks for c in t.clips] == [500]


def test_an_entry_with_more_slots_than_tracks_folds_onto_the_last_track():
    e = entry(ClipRef("a" * 64, 0, 100, track_slot=0),
              ClipRef("a" * 64, 0, 100, track_slot=5))
    got, _ = preview_project(project(), e)
    assert [len(t.clips) for t in got.tracks] == [1, 1]


def test_nothing_playable_gives_none():
    got, missing = preview_project(project(), entry(ClipRef("f" * 64, 0, 1_000)))
    assert got is None
    assert missing == ("f" * 64,)
