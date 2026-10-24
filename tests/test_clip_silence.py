"""Auto-Silence belongs to the clip it measured, so it travels with that clip."""

import numpy as np

from kuulas import analysis, mixer, ops
from kuulas.clock import frames_to_flicks
from kuulas.model import Clip, Media, Project
from kuulas.transcript import timeline_words


class MemoryStore:
    def __init__(self, arrays):
        self.arrays = arrays

    def read(self, media_id, first, count):
        source = self.arrays[media_id]
        out = np.zeros((source.shape[0], count), dtype=np.float32)
        piece = source[:, max(0, first):first + count]
        out[:, :piece.shape[1]] = piece
        return out


def project_with_clip():
    project = Project(rate=1000)
    project = ops.add_media(project, Media(id="m", name="m.wav", channels=1, frames=2000))
    project = ops.add_track(project, track_id="t", name="T")
    return ops.add_clip(project, track_id="t", media_id="m", clip_id="c")


def test_clip_silence_ranges_round_trip_and_are_omitted_when_empty():
    clip = Clip(id="c", media="m", start=0, offset=0, length=1000,
                auto_silence=((100, 200),))

    assert Clip.from_dict(clip.to_dict()) == clip
    assert "auto_silence" not in Clip(id="x", media="m", start=0, offset=0,
                                       length=1000).to_dict()


def test_auto_silence_is_attached_in_source_frames_and_moves_with_clip():
    project = project_with_clip()
    project = analysis.apply_silence(project, {"t": ((100, 200),)})
    clip = project.track("t").clips[0]
    assert clip.auto_silence == ((100, 200),)
    assert not project.track("t").gate

    moved = ops.move_clip(project, "c", 500)

    assert moved.track("t").clips[0].auto_silence == ((100, 200),)
    assert analysis.current_silence_ranges(moved) == {"t": ((600, 700),)}
    store = MemoryStore({"m": np.ones((1, 2000), dtype=np.float32)})
    assert not mixer.mix(moved, store, 600, 100).any()
    assert mixer.mix(moved, store, 500, 100).any()

    other = ops.add_track(moved, track_id="u", name="U")
    other = ops.add_clip(other, track_id="u", media_id="m", start=600, clip_id="d")
    other = ops.move_clip(other, "d", 600, "t")
    assert mixer.mix(other, store, 600, 100).any(), (
        "new clips do not inherit another clip's silence")


def test_opening_one_implicit_region_makes_only_that_portion_a_real_clip():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200),)})

    opened = ops.open_gated_region(project, "t", 150)

    clips = opened.track("t").clips
    assert [(clip.start, clip.end, clip.muted, clip.auto_silence) for clip in clips] == [
        (0, 100, False, ((100, 200),)),
        (100, 200, False, ()),
        (200, 2000, False, ((100, 200),)),
    ]
    muted = ops.set_clip(opened, clips[1].id, muted=True)
    assert [clip.muted for clip in muted.track("t").clips] == [False, True, False]


def test_dragging_an_implicit_edge_materializes_and_trims_just_that_region():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200),)})

    dragged = ops.trim_auto_silence_edge(project, "c", 100, 200, "start", 120)

    assert [(clip.start, clip.end, clip.muted) for clip in dragged.track("t").clips] == [
        (0, 120, False),
        (120, 200, True),
        (200, 2000, False),
    ]
    assert all(not clip.auto_silence for clip in dragged.track("t").clips if clip.muted)


def test_transcript_marks_words_inside_the_clip_silence_as_muted():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200),)})
    words = [{"w": "quiet", "s": frames_to_flicks(140, 1000),
              "e": frames_to_flicks(160, 1000)}]

    assert timeline_words(project, {"m": words})[0]["muted"] is True
