"""Gated frames count as inaudible everywhere a muted clip does (WP44)."""

import numpy as np

from kuulas import (
    analysis,
    collateral,
    edit_points,
    gate,
    onsets,
    ops,
    source_map,
    transcript,
)
from kuulas.clock import FLICKS, frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.music_report import build_report
from kuulas.usage import extract

RATE = 48_000


def one_track(gate_ranges=(), clips=None, **track_fields):
    clips = clips or (Clip("c", "m", 0, 0, 10_000),)
    track = Track("t", "Voice", kind="speech", clips=tuple(clips),
                  gate=tuple(gate_ranges), **track_fields)
    return Project(rate=RATE, media=(Media("m", "m.wav", 1, 200_000, sha256="a" * 64),),
                   tracks=(track,))


# -- the gate helpers --------------------------------------------------------


def test_closed_at_is_half_open():
    g = ((10, 20), (40, 50))
    assert [gate.closed_at(g, f) for f in (9, 10, 19, 20, 39, 40, 49, 50)] == [
        False, True, True, False, False, True, True, False]


def test_split_by_gate_cuts_a_span_at_the_gate_edges():
    g = ((10, 20), (40, 50))
    assert gate.split_by_gate(g, 0, 60) == [
        (0, 10, True), (10, 20, False), (20, 40, True), (40, 50, False), (50, 60, True)]
    assert gate.split_by_gate(g, 12, 18) == [(12, 18, False)]
    assert gate.split_by_gate(g, 20, 40) == [(20, 40, True)]
    assert gate.split_by_gate((), 5, 9) == [(5, 9, True)]


# -- usage, source map, collateral ------------------------------------------


def test_usage_marks_the_gated_part_of_a_clip_inaudible():
    uses = extract(one_track([(2_000, 3_000)]), merge_gap=0)
    assert [(u.timeline_from, u.timeline_to, u.audible) for u in uses] == [
        (0, 2_000, True), (2_000, 3_000, False), (3_000, 10_000, True)]
    # The source clock follows: the gated stretch is the matching recording range.
    assert uses[1].from_flicks == frames_to_flicks(2_000, RATE)


def test_usage_gate_and_automation_both_apply():
    p = one_track([(0, 1_000)], automation=((0, 0.0), (5_000, 0.0), (5_001, -80.0)))
    uses = extract(p, merge_gap=0)
    assert [(u.timeline_from, u.timeline_to, u.audible) for u in uses[:2]] == [
        (0, 1_000, False), (1_000, 5_000, True)]
    assert uses[-1].audible is False


def test_a_gated_track_covers_as_cut_in_the_source_map():
    used, cut, _unused = source_map.coverage(one_track([(2_000, 3_000)]), "a" * 64)
    assert cut == [(frames_to_flicks(2_000, RATE), frames_to_flicks(3_000, RATE))]
    assert used[0][0] == 0


def test_collateral_audio_leaves_out_gated_frames():
    p = one_track(clips=(Clip("c", "m", 0, 0, 10_000),))
    other = Track("o", "Other", kind="speech", clips=(Clip("d", "m", 0, 0, 10_000),),
                  gate=((3_000, 4_000),))
    p = Project(rate=RATE, media=p.media, tracks=(*p.tracks, other))
    words = {"m": [{"w": "x", "s": frames_to_flicks(1_000, RATE),
                    "e": frames_to_flicks(8_000, RATE)}]}
    c = collateral.cut_collateral(p, words, [{"track": "t", "clip": "c", "index": 0}])
    assert c.audio["o"] == [(1_000, 3_000), (4_000, 8_000)]


# -- the music report --------------------------------------------------------


class MemoryStore:
    def __init__(self, arrays):
        self.arrays = arrays

    def read(self, media_id, first, count):
        a = self.arrays[media_id]
        out = np.zeros((a.shape[0], count), dtype=np.float32)
        lo, hi = max(0, first), min(a.shape[1], first + count)
        if hi > lo:
            out[:, lo - first:hi - first] = a[:, lo:hi]
        return out


def report_project(speech_gate):
    frames = 4 * RATE
    speech_media = Media("s", "s.wav", 1, frames, sha256="s" * 64)
    music = Media("mu", "mu.wav", 2, 200_000, sha256="u" * 64,
                  extra={"music_info": {"title": "Bed", "artist": "A"}})
    return Project(rate=RATE, media=(speech_media, music), tracks=(
        Track("sp", "Speech", kind="speech", gate=speech_gate,
              clips=(Clip("sc", "s", 0, 0, frames),)),
        Track("mu", "Music", kind="music",
              clips=(Clip("mc", "mu", RATE // 2, 0, RATE),)),
    ))


def test_music_report_ignores_speech_that_is_gated():
    audio = np.zeros(4 * RATE, dtype=np.float32)
    audio[:2 * RATE] = 0.3 * np.random.default_rng(2).standard_normal(2 * RATE)
    store = MemoryStore({"s": audio[None, :]})
    assert [r.background for r in build_report(report_project(()), store)] == [True]
    gated = report_project(((0, 3 * RATE),))
    assert [r.background for r in build_report(gated, store)] == [False]


def test_music_report_skips_music_that_is_gated():
    p = report_project(())
    music = p.tracks[1]
    p = Project(rate=RATE, media=p.media, tracks=(
        p.tracks[0], Track(**{**music.__dict__, "gate": ((0, 3 * RATE),)})))
    assert build_report(p, MemoryStore({"s": np.zeros((1, 4 * RATE), np.float32)})) == ()


# -- words, edit points, onsets, levels --------------------------------------

W = {"m": [{"w": w, "s": round(s * FLICKS), "e": round(e * FLICKS), "spk": "A"}
           for w, s, e in (("hei", 0, 0.5), ("tama", 1.0, 1.5), ("on", 2.0, 2.5))]}


def words_project(gate_ranges):
    p = Project(rate=1000)
    p = ops.add_media(p, Media(id="m", name="a.wav", channels=1, frames=10_000))
    p = ops.add_track(p, track_id="t", name="A")
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c")
    return ops.set_gate(p, "t", gate_ranges)


def test_gated_words_are_flagged_muted_like_muted_clips():
    tw = transcript.timeline_words(words_project([(900, 1600)]), W)
    assert [(w["w"], w["muted"]) for w in tw] == [
        ("hei", False), ("tama", True), ("on", False)]


def test_a_word_is_gated_by_its_midpoint():
    tw = transcript.timeline_words(words_project([(0, 300)]), W)  # hei: mid 250
    assert tw[0]["muted"] is True
    tw = transcript.timeline_words(words_project([(0, 200)]), W)
    assert tw[0]["muted"] is False


def test_word_edit_points_skip_gated_words():
    pts = edit_points.edit_points(words_project([(900, 1600)]), W, {}, "words")
    assert pts == [0, 2000]


def test_edge_points_drop_clip_edges_in_the_gate_and_add_the_gate_edges():
    p = one_track([(0, 1_000), (9_000, 10_000)])
    assert edit_points.edit_points(p, {}, {}, "edges") == [0, 1_000, 9_000, 10_000]
    p = one_track([(2_000, 3_000)])
    assert edit_points.edit_points(p, {}, {}, "edges") == [0, 2_000, 3_000, 10_000]


def test_onsets_inside_the_gate_are_skipped():
    p = one_track([(2_000, 3_000)])
    flicks = [frames_to_flicks(f, RATE) for f in (1_000, 2_500, 5_000)]
    assert onsets.timeline_onsets(p, {"m": flicks}) == [1_000, 5_000]


def talkers():
    rng = np.random.default_rng(3)
    n = 12 * RATE // 6  # 12 s at 8 kHz
    sig = np.zeros(n, dtype=np.float32)
    sig[: n // 2] = 0.3 * rng.standard_normal(n // 2)
    p = Project(rate=RATE // 6)
    p = ops.add_media(p, Media(id="m", name="a.wav", channels=1, frames=n))
    p = ops.add_track(p, track_id="t", name="A")
    p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c")
    return p, MemoryStore({"m": sig[None, :]})


def test_track_levels_treat_gated_hops_as_not_there():
    p, store = talkers()
    db, valid = analysis.track_levels(p, store, p.track("t"))
    assert valid.all()
    q = ops.set_gate(p, "t", [(0, 4 * p.rate)])
    db2, valid2 = analysis.track_levels(q, store, q.track("t"))
    hop = analysis.hop_frames(p.rate)
    first_open = 4 * p.rate // hop
    assert not valid2[:first_open].any()
    assert valid2[first_open:].all()
    assert (db2[:first_open] == db2.min()).all()
    assert np.array_equal(db2[first_open:], db[first_open:])
