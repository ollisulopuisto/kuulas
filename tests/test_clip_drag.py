"""Dragging a clip body (WP6): move_clips_to_track is nudge_clips plus a track change."""

from kuulas import ops
from kuulas.model import Media, Project

RATE = 48000
S = RATE


def project() -> Project:
    """Anna, Ville (one sync group) and Music (none); tracks in that order, 10 s clips."""
    p = Project(rate=RATE)
    for m in ("ma", "mv", "mm"):
        p = ops.add_media(p, Media(id=m, name=f"{m}.wav", channels=1, frames=10 * S))
    for t in ("A", "V", "M"):
        p = ops.add_track(p, track_id=t, name=t)
    p = ops.add_clip(p, "A", "ma", clip_id="ca")
    p = ops.add_clip(p, "V", "mv", clip_id="cv")
    p = ops.add_clip(p, "M", "mm", clip_id="cm")
    return ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")


def where(p: Project, clip_id: str):
    for t in p.tracks:
        for c in t.clips:
            if c.id == clip_id:
                return t.id, c.start
    return None


def test_registered_as_an_edit():
    assert "move_clips_to_track" in ops.OPS


def test_one_track_down_and_later():
    p = ops.move_clips_to_track(project(), ["cm"], 0, delta=S)
    assert where(p, "cm") == ("M", S)
    p = ops.move_clips_to_track(project(), ["ca"], 2, delta=S)
    assert where(p, "ca") == ("M", S)


def test_direction_is_clamped_to_the_tracks():
    p = ops.move_clips_to_track(project(), ["cm"], 5)
    assert where(p, "cm") == ("M", 0)
    p = ops.move_clips_to_track(project(), ["cv"], -5)
    assert where(p, "cv") == ("A", 0)


def test_selection_keeps_its_shape_when_one_clip_hits_the_edge():
    p = ops.move_clips_to_track(project(), ["cv", "cm"], 1)
    assert where(p, "cv") == ("V", 0)
    assert where(p, "cm") == ("M", 0)


def test_sync_partners_never_follow():
    p = ops.move_clips_to_track(project(), ["ca"], 0, delta=S // 2)
    assert where(p, "ca") == ("A", S // 2)
    assert where(p, "cv") == ("V", 0)


def test_an_explicit_group_moves_together_in_time_and_track():
    p = ops.group_clips(project(), ["ca", "cv"])
    p = ops.move_clips_to_track(p, ["ca"], 1, delta=S // 2)
    assert where(p, "ca") == ("V", S // 2)
    assert where(p, "cv") == ("M", S // 2)


def test_never_before_zero():
    p = ops.move_clips_to_track(project(), ["ca"], 0, delta=-S)
    assert where(p, "ca") == ("A", 0)
