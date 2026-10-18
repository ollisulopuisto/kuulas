"""Deleting tracks once they are empty (owner, 2026-10-19)."""

import pytest

from kuulas import ops
from kuulas.model import Media, Project

RATE = 48000


def project() -> Project:
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m", name="m.wav", channels=1, frames=10 * RATE))
    for t in ("A", "B", "C"):
        p = ops.add_track(p, track_id=t, name=t)
    return ops.add_clip(p, "B", "m", clip_id="cb")


def ids(p: Project) -> list[str]:
    return [t.id for t in p.tracks]


def test_registered_as_an_edit():
    assert "delete_empty_tracks" in ops.OPS


def test_every_empty_track_goes_and_the_others_stay_in_order():
    assert ids(ops.delete_empty_tracks(project())) == ["B"]


def test_a_track_with_a_clip_is_never_removed():
    p = ops.delete_empty_tracks(project())
    assert [c.id for t in p.tracks for c in t.clips] == ["cb"]


def test_nothing_empty_is_an_error_so_the_menu_can_say_so():
    p = ops.delete_empty_tracks(project())
    with pytest.raises(ops.EditError):
        ops.delete_empty_tracks(p)
