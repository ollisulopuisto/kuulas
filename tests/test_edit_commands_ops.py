"""The ops behind the editing keys (WP5): each is one OPS entry, so one undo step."""

import numpy as np
import pytest
from pedalboard.io import AudioFile

from kuulas import ops
from kuulas.model import Media, Project
from kuulas.session import Session

RATE = 48000
S = RATE


def project() -> Project:
    """Anna, Ville (in one sync group) and Music (in none); each one 10 s clip."""
    p = Project(rate=RATE)
    for m in ("ma", "mv", "mm"):
        p = ops.add_media(p, Media(id=m, name=f"{m}.wav", channels=1, frames=10 * S))
    for t in ("A", "V", "M"):
        p = ops.add_track(p, track_id=t, name=t)
    p = ops.add_clip(p, "A", "ma", clip_id="ca")
    p = ops.add_clip(p, "V", "mv", clip_id="cv")
    p = ops.add_clip(p, "M", "mm", clip_id="cm")
    return ops.mark_in_sync(p, ["ca", "cv"], main="ca", group_id="g")


def spans(p: Project, track: str):
    return [(c.start, c.end, c.muted) for c in p.track(track).clips]


def test_all_new_ops_are_in_the_edit_table():
    for name in ("split_clips", "mute_range", "cut_range", "nudge_clips",
                 "trim_clips", "adjust_clip_gain"):
        assert name in ops.OPS


def test_split_clips_cuts_every_listed_clip_the_point_is_inside():
    p = ops.split_clips(project(), 4 * S, ["ca", "cv"])
    assert [(a, b) for a, b, _ in spans(p, "A")] == [(0, 4 * S), (4 * S, 10 * S)]
    assert [(a, b) for a, b, _ in spans(p, "V")] == [(0, 4 * S), (4 * S, 10 * S)]
    assert len(p.track("M").clips) == 1


def test_split_clips_skips_clips_that_do_not_hold_the_point():
    p = ops.add_clip(project(), "M", "mm", clip_id="cm2", start=20 * S, length=S)
    p = ops.split_clips(p, 4 * S, ["cm", "cm2"])
    assert len(p.track("M").clips) == 3


def test_split_clips_with_nothing_to_split_is_refused():
    with pytest.raises(ops.EditError) as error:
        ops.split_clips(project(), 11 * S, ["ca"])
    assert error.value.key == "error.edit.split_outside"


def test_mute_range_mutes_the_stretch_on_the_given_tracks_only():
    p = ops.mute_range(project(), 2 * S, 4 * S, ["M"])
    assert [(a, b) for a, b, m in spans(p, "M") if m] == [(2 * S, 4 * S)]
    assert not any(m for _, _, m in spans(p, "A"))
    assert [c.start for c in p.track("M").clips] == [0, 2 * S, 4 * S]  # nothing moved


def test_mute_range_never_follows_the_sync_group():
    p = ops.mute_range(project(), 2 * S, 4 * S, ["A"])
    assert any(m for _, _, m in spans(p, "A"))
    assert not any(m for _, _, m in spans(p, "V"))


def test_mute_range_without_tracks_acts_on_all_tracks():
    p = ops.mute_range(project(), 2 * S, 4 * S, None)
    for track in ("A", "V", "M"):
        assert [(a, b) for a, b, m in spans(p, track) if m] == [(2 * S, 4 * S)]


def test_mute_range_empty_is_refused():
    with pytest.raises(ops.EditError) as error:
        ops.mute_range(project(), 4 * S, 4 * S, ["A"])
    assert error.value.key == "error.edit.empty_range"


def test_cut_range_cuts_only_the_given_tracks_sync_is_not_a_scope():
    p = ops.cut_range(project(), 2 * S, 4 * S, ["A"])
    assert p.track("A").clips[-1].end == 8 * S
    assert p.track("V").clips[-1].end == 10 * S
    assert p.track("M").clips[-1].end == 10 * S


def test_cut_range_without_tracks_cuts_all_tracks():
    p = ops.cut_range(project(), 2 * S, 4 * S, None)
    assert [p.track(t).clips[-1].end for t in "AVM"] == [8 * S] * 3


def test_cut_range_empty_is_refused():
    with pytest.raises(ops.EditError):
        ops.cut_range(project(), 4 * S, 2 * S, ["A"])


def test_nudge_clips_never_takes_sync_partners_along():
    p = ops.nudge_clips(project(), ["ca"], S // 100)
    assert p.clip("ca").start == S // 100
    assert p.clip("cv").start == 0


def test_nudge_clips_takes_an_explicit_group_along():
    p = ops.group_clips(project(), ["ca", "cm"])
    p = ops.nudge_clips(p, ["ca"], S // 100)
    assert p.clip("ca").start == S // 100
    assert p.clip("cm").start == S // 100
    assert p.clip("cv").start == 0


def test_nudge_clips_never_goes_before_zero():
    p = ops.nudge_clips(project(), ["ca"], -S)
    assert p.clip("ca").start == 0


def test_trim_clips_trims_each_to_the_point():
    p = ops.trim_clips(project(), ["ca", "cv"], start=3 * S)
    assert (p.clip("ca").start, p.clip("cv").start) == (3 * S, 3 * S)
    p = ops.trim_clips(project(), ["ca", "cv"], end=3 * S)
    assert (p.clip("ca").end, p.clip("cv").end) == (3 * S, 3 * S)


def test_trim_clips_outside_a_clip_is_refused_and_changes_nothing():
    with pytest.raises(ops.EditError) as error:
        ops.trim_clips(project(), ["ca"], start=11 * S)
    assert error.value.key == "error.edit.trim_empty"


def test_adjust_clip_gain_adds_the_step_and_stays_in_the_inspector_range():
    p = ops.adjust_clip_gain(project(), ["ca", "cv"], 0.5)
    assert (p.clip("ca").gain_db, p.clip("cv").gain_db) == (0.5, 0.5)
    p = ops.adjust_clip_gain(p, ["ca"], -0.5)
    assert p.clip("ca").gain_db == 0.0
    assert ops.adjust_clip_gain(project(), ["ca"], 100).clip("ca").gain_db == 12.0
    assert ops.adjust_clip_gain(project(), ["ca"], -100).clip("ca").gain_db == -60.0


def test_adjust_clip_gain_without_clips_is_refused():
    with pytest.raises(ops.EditError) as error:
        ops.adjust_clip_gain(project(), [], 0.5)
    assert error.value.key == "error.edit.no_selection"


def test_an_op_is_one_undo_step_through_the_edit_endpoint(tmp_path):
    session = Session(tmp_path / "t.kuulas")
    try:
        for name in ("a.wav", "b.wav"):
            path = str(tmp_path / name)
            with AudioFile(path, "w", samplerate=RATE, num_channels=1) as f:
                f.write(np.full((1, 4 * RATE), 0.1, dtype=np.float32))
        session.import_media([str(tmp_path / "a.wav"), str(tmp_path / "b.wav")])
        tracks = [t.id for t in session.state.tracks]
        steps = len(session.history.nodes())
        session.edit("mute_range", {"start": S, "end": 2 * S, "track_ids": tracks[:1],
                                    "group_editing": False})
        assert len(session.history.nodes()) == steps + 1
        assert any(c.muted for c in session.state.track(tracks[0]).clips)
        assert session.undo()
        assert not any(c.muted for t in session.state.tracks for c in t.clips)
    finally:
        session.close()


def test_quick_mute_stretch_splits_at_both_edges():
    """Quick mute (ui/quick-mute.js) sends mute_range, 0.25 s each side of the cursor."""
    p = ops.mute_range(project(), 5 * S - S // 4, 5 * S + S // 4, ["A"])
    assert spans(p, "A") == [
        (0, 5 * S - S // 4, False),
        (5 * S - S // 4, 5 * S + S // 4, True),
        (5 * S + S // 4, 10 * S, False),
    ]


def test_quick_mute_at_a_clip_edge_is_clamped_to_the_clip():
    p = ops.mute_range(project(), -S // 4, S // 4, ["A"])
    assert spans(p, "A") == [(0, S // 4, True), (S // 4, 10 * S, False)]
    p = ops.mute_range(project(), 10 * S - S // 4, 10 * S + S // 4, ["A"])
    assert spans(p, "A")[-1] == (10 * S - S // 4, 10 * S, True)
