from __future__ import annotations

import pytest

from kuulas import edit_scope, history, ops
from kuulas.model import Media, Project

RATE = 48000


def make_project_with_group() -> Project:
    """Project with 3 sync-grouped tracks (A, V, Z) and 1 ungrouped track (M)."""
    p = Project(rate=RATE)
    # Media
    ma = Media(id="ma", name="anna.wav", channels=1, frames=100 * RATE)
    mv = Media(id="mv", name="ville.wav", channels=1, frames=100 * RATE)
    mz = Media(id="mz", name="zoom.wav", channels=1, frames=100 * RATE)
    mm = Media(id="mm", name="music.wav", channels=2, frames=100 * RATE)
    p = ops.add_media(p, ma)
    p = ops.add_media(p, mv)
    p = ops.add_media(p, mz)
    p = ops.add_media(p, mm)

    # Tracks
    p = ops.add_track(p, track_id="A", name="Anna")
    p = ops.add_track(p, track_id="V", name="Ville")
    p = ops.add_track(p, track_id="Z", name="Zoom")
    p = ops.add_track(p, track_id="M", name="Music")

    # Clips
    p = ops.add_clip(p, "A", "ma", clip_id="ca", start=0, offset=0, length=100 * RATE)
    p = ops.add_clip(p, "V", "mv", clip_id="cv", start=0, offset=0, length=100 * RATE)
    p = ops.add_clip(p, "Z", "mz", clip_id="cz", start=0, offset=0, length=100 * RATE)
    p = ops.add_clip(p, "M", "mm", clip_id="cm", start=0, offset=0, length=100 * RATE)

    # Mark A, V, Z in sync
    return ops.mark_in_sync(p, ["ca", "cv", "cz"], main="ca", group_id="g_speech")


def test_partners_found_by_recording_time_not_timeline_overlap():
    p = Project(rate=RATE)
    ma = Media(id="ma", name="anna.wav", channels=1, frames=100 * RATE)
    mv = Media(id="mv", name="ville.wav", channels=1, frames=100 * RATE)
    p = ops.add_media(p, ma)
    p = ops.add_media(p, mv)
    p = ops.add_track(p, track_id="A", name="Anna")
    p = ops.add_track(p, track_id="V", name="Ville")

    # Clip ca: recorded range [1000, 3000], timeline [0, 2000]
    p = ops.add_clip(p, "A", "ma", clip_id="ca", start=0, offset=1000, length=2000)
    # Clip cv_drifted: recorded range [1000, 3000], timeline [50000, 52000]
    # (does NOT overlap timeline of ca)
    p = ops.add_clip(
        p, "V", "mv", clip_id="cv_drifted", start=50000, offset=1000, length=2000
    )
    # Clip cv_overlap: recorded range [90000, 92000], timeline [0, 2000]
    # (overlaps timeline of ca, but different recording time)
    p = ops.add_clip(
        p, "V", "mv", clip_id="cv_overlap", start=0, offset=90000, length=2000
    )

    p = ops.mark_in_sync(
        p, ["ca", "cv_drifted", "cv_overlap"], main="ca", group_id="g", basis="files"
    )
    material = {"sync": history.sync_root(p.sync_groups)}

    # Partners of ca should find cv_drifted (same recording stretch), NOT cv_overlap
    ca_partners = edit_scope.partners(p, material, "ca")
    partner_ids = [c.id for c in ca_partners]
    assert partner_ids == ["cv_drifted"]

    # cv_drifted partners should be ca
    cv_drifted_partners = edit_scope.partners(p, material, "cv_drifted")
    assert [c.id for c in cv_drifted_partners] == ["ca"]

    # cv_overlap has no partners
    cv_overlap_partners = edit_scope.partners(p, material, "cv_overlap")
    assert cv_overlap_partners == []


def test_sync_is_not_a_scope_for_a_range():
    """WP83: a range names its tracks; the sync group never widens it."""
    p = make_project_with_group()
    assert edit_scope.range_tracks(p, ["A"]) == ["A"]
    assert edit_scope.range_tracks(p, ["M"]) == ["M"]


def test_no_tracks_given_means_all_tracks():
    p = make_project_with_group()
    assert edit_scope.range_tracks(p) == ["A", "V", "Z", "M"]
    assert edit_scope.range_tracks(p, []) == ["A", "V", "Z", "M"]


def test_range_tracks_accepts_track_objects_and_keeps_project_order():
    p = make_project_with_group()
    assert edit_scope.range_tracks(p, [p.track("V"), "A", "V"]) == ["A", "V"]


def test_range_tracks_rejects_an_unknown_track():
    with pytest.raises(KeyError):
        edit_scope.range_tracks(make_project_with_group(), ["nope"])


def test_expand_clips_never_adds_sync_partners():
    p = make_project_with_group()
    assert edit_scope.expand_clips(p, ["ca"]) == ["ca"]


def test_expand_clips_adds_the_members_of_an_explicit_group_only():
    p = make_project_with_group()
    p = ops.group_clips(p, ["ca", "cm"])
    assert set(edit_scope.expand_clips(p, ["ca"])) == {"ca", "cm"}
    assert edit_scope.expand_clips(p, ["cv"]) == ["cv"]


def test_partners_with_none_material():
    """Partners works when material is None (reading from p.sync_groups directly)."""
    p = make_project_with_group()
    ca_partners = edit_scope.partners(p, None, "ca")
    assert {c.id for c in ca_partners} == {"cv", "cz"}


def test_partners_partial_recording_overlap():
    """Clips overlap on recording clock partially."""
    p = Project(rate=RATE)
    ma = Media(id="ma", name="a.wav", channels=1, frames=100 * RATE)
    mv = Media(id="mv", name="v.wav", channels=1, frames=100 * RATE)
    mz = Media(id="mz", name="z.wav", channels=1, frames=100 * RATE)
    p = ops.add_media(p, ma)
    p = ops.add_media(p, mv)
    p = ops.add_media(p, mz)
    p = ops.add_track(p, track_id="A", name="A")
    p = ops.add_track(p, track_id="V", name="V")
    p = ops.add_track(p, track_id="Z", name="Z")

    # ca: offset 1000..3000
    p = ops.add_clip(p, "A", "ma", clip_id="ca", start=0, offset=1000, length=2000)
    # cv: offset 2500..4000 (overlaps 2500..3000 with ca)
    p = ops.add_clip(p, "V", "mv", clip_id="cv", start=0, offset=2500, length=1500)
    # cz: offset 3500..5000 (does not overlap ca, but overlaps cv)
    p = ops.add_clip(p, "Z", "mz", clip_id="cz", start=0, offset=3500, length=1500)

    p = ops.mark_in_sync(p, ["ca", "cv", "cz"], main="ca", group_id="g", basis="files")

    ca_partners = edit_scope.partners(p, None, "ca")
    assert [c.id for c in ca_partners] == ["cv"]

    cv_partners = edit_scope.partners(p, None, "cv")
    assert {c.id for c in cv_partners} == {"ca", "cz"}


def test_partners_nonexistent_or_ungrouped_clip():
    p = make_project_with_group()
    # Nonexistent clip
    assert edit_scope.partners(p, None, "nonexistent") == []
    # Clip cm is on Music track M (not in any sync group)
    assert edit_scope.partners(p, None, "cm") == []


def test_partners_multiple_clips_on_same_track():
    """If another track is split into two pieces that both overlap, both are returned."""
    p = Project(rate=RATE)
    ma = Media(id="ma", name="a.wav", channels=1, frames=100 * RATE)
    mv = Media(id="mv", name="v.wav", channels=1, frames=100 * RATE)
    p = ops.add_media(p, ma)
    p = ops.add_media(p, mv)
    p = ops.add_track(p, track_id="A", name="A")
    p = ops.add_track(p, track_id="V", name="V")

    # Anna plays 0..10000
    p = ops.add_clip(p, "A", "ma", clip_id="ca", start=0, offset=0, length=10000)
    # Ville piece 1: 0..4000
    p = ops.add_clip(p, "V", "mv", clip_id="cv1", start=0, offset=0, length=4000)
    # Ville piece 2: 5000..9000
    p = ops.add_clip(p, "V", "mv", clip_id="cv2", start=6000, offset=5000, length=4000)

    p = ops.mark_in_sync(p, ["ca", "cv1", "cv2"], main="ca", group_id="g", basis="files")

    partners = edit_scope.partners(p, None, "ca")
    assert [c.id for c in partners] == ["cv1", "cv2"]
