"""Auto-Silence belongs to the clip it measured, so it travels with that clip."""

from dataclasses import replace

import numpy as np

from kuulas import analysis, edit_scope, mixer, ops
from kuulas.clock import frames_to_flicks
from kuulas.history import History
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


def test_dragging_a_clip_converts_its_legacy_track_gate_to_clip_silence():
    project = ops.add_track(project_with_clip(), track_id="u", name="U")
    project = ops.set_gate(project, "t", ((100, 200),))
    project = ops.set_gate(project, "u", ((500, 600),))

    moved = ops.move_clips_to_track(project, ["c"], 1, delta=500)

    clip = moved.track("u").clips[0]
    assert clip.auto_silence == ((100, 200),)
    assert moved.track("t").gate == ()
    assert moved.track("u").gate == ()
    assert analysis.current_silence_ranges(moved) == {"u": ((600, 700),)}
    store = MemoryStore({"m": np.ones((1, 2000), dtype=np.float32)})
    assert not mixer.mix(moved, store, 600, 100).any()
    assert mixer.mix(moved, store, 500, 100).any(), (
        "a clip moved to a legacy-gated track must not inherit its gate")


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


def test_opening_an_implicit_region_targets_the_clicked_clip_when_clips_overlap():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200),)})
    first = project.track("t").clips[0]
    second = replace(first, id="overlap")
    track = replace(project.track("t"), clips=(first, second))
    project = replace(project, tracks=(track,))

    opened = ops.open_gated_region(project, "t", 150, clip_id="overlap")

    clips = opened.track("t").clips
    targeted = [clip for clip in clips if clip.start == 100 and clip.end == 200]
    assert len(targeted) == 1
    assert targeted[0].muted is False
    assert targeted[0].auto_silence == ()
    untouched = next(clip for clip in clips if clip.id == first.id)
    assert untouched.auto_silence == ((100, 200),)
    muted = ops.set_clip(opened, targeted[0].id, muted=True)
    muted_clips = muted.track("t").clips
    assert next(clip for clip in muted_clips if clip.id == targeted[0].id).muted
    assert not next(clip for clip in muted_clips if clip.id == first.id).muted


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


def test_muting_an_open_implicit_portion_does_not_mute_the_parent():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200), (300, 400))})
    changed = ops.open_gated_region(project, "t", 250, clip_id="c", muted=True)
    clips = changed.track("t").clips
    assert [(c.start, c.end, c.muted) for c in clips] == [
        (0, 200, False), (200, 300, True), (300, 2000, False)]
    assert clips[1].ungated
    assert clips[1].offset == 200
    assert not clips[1].auto_silence


def test_legacy_gate_opening_has_the_same_portion_target():
    project = ops.set_gate(project_with_clip(), "t", ((100, 200), (300, 400)))
    changed = ops.open_gated_region(project, "t", 250, clip_id="c", muted=True)
    target = next(c for c in changed.track("t").clips if c.start == 200)
    assert (target.end, target.muted, target.ungated) == (300, True, True)
    assert not changed.track("t").clips[0].muted


def test_materialized_portion_stays_explicit_after_move_and_new_auto_silence():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200),)})
    project = ops.open_gated_region(project, "t", 150, clip_id="c")
    target = next(c for c in project.track("t").clips if c.start == 100)
    assert target.ungated
    project = ops.move_clip(project, target.id, 500)
    project = analysis.apply_silence(project, {"t": ((0, 2000),)})
    target = next(c for c in project.track("t").clips if c.id == target.id)
    assert target.ungated
    assert not target.auto_silence
    assert not target.muted
    assert Clip.from_dict(target.to_dict()).ungated


def test_dragging_the_open_side_of_a_dotted_edge_keeps_it_audible_and_explicit():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200), (300, 400))})
    changed = ops.trim_auto_silence_edge(project, "c", 200, 300, "end", 340)
    target = next(c for c in changed.track("t").clips if c.start == 200)
    assert (target.end, target.muted, target.ungated, target.auto_silence) == (
        340, False, True, ())
    changed = analysis.apply_silence(changed, {"t": ((0, 2000),)})
    target = next(c for c in changed.track("t").clips if c.id == target.id)
    assert not target.auto_silence
    assert not target.muted


def test_materialized_portion_can_toggle_independently_of_the_parent_group():
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200),)})
    track = project.track("t")
    project = replace(project, tracks=(replace(
        track, clips=(replace(track.clips[0], group="g"),)),))
    opened = ops.open_gated_region(project, "t", 150, clip_id="c")
    target = next(c for c in opened.track("t").clips if c.start == 100)
    assert edit_scope.expand_clips(opened, [target.id]) == [target.id]
    assert not target.group


def test_materializing_a_portion_is_one_undoable_persistent_step(tmp_path):
    project = analysis.apply_silence(project_with_clip(), {"t": ((100, 200), (300, 400))})
    path = tmp_path / "project.sqlite"
    history = History(path, initial=project)
    history.db.execute(
        "insert into media(id, sha256, name, storage, channels, source_rate,"
        " source_frames, lossless, added_utc) values"
        " ('m', ?, 'm.wav', 'working', 1, 1000, 2000, 1, '2026-10-24T00:00:00Z')",
        ("a" * 64,))
    project = history.state
    changed = ops.open_gated_region(project, "t", 250, clip_id="c", muted=True)
    history.commit("mute portion", changed)
    history.undo()
    assert history.state == project
    history.redo()
    assert history.state == changed
    history.close()
    history = History(path)
    try:
        target = next(c for c in history.state.track("t").clips if c.start == 200)
        assert target.muted
        assert target.ungated
        assert not target.auto_silence
    finally:
        history.close()


def test_legacy_dotted_border_drag_materializes_only_the_grabbed_clip():
    project = ops.set_gate(project_with_clip(), "t", ((100, 200), (300, 400)))
    changed = ops.trim_auto_silence_edge(project, "c", 200, 300, "start", 180)
    target = next(c for c in changed.track("t").clips if c.start == 180)
    assert (target.end, target.muted, target.ungated) == (300, False, True)
    assert changed.track("t").gate == ((100, 180), (300, 400))
