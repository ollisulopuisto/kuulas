"""Cut candidates (WP18): detection, merging with decisions, placement, apply plans.

Pure logic: a project, its transcripts (flicks from each media's start) and
optional silence data in, candidates and plans out. Nothing here reads audio.
"""

from __future__ import annotations

import time
from dataclasses import replace

import pytest

from kuulas import candidates as cm
from kuulas import ops
from kuulas.clock import FLICKS, frames_to_flicks
from kuulas.model import Clip, Media, Project, SyncGroup, Track

RATE = 48000


def f(seconds: float) -> int:
    """Seconds as flicks."""
    return round(seconds * FLICKS)


def fr(seconds: float) -> int:
    """Seconds as project frames."""
    return round(seconds * RATE)


def words(*spec) -> list[dict]:
    """``(text, start_s, end_s)`` triples as stored transcript words."""
    return [{"w": w, "s": f(s), "e": f(e), "spk": "A"} for w, s, e in spec]


def media(mid: str, seconds: float = 60.0) -> Media:
    return Media(id=mid, name=mid, channels=1, frames=fr(seconds),
                 sha256=(mid * 64)[:64])


def project(*tracks: tuple[str, str], groups=()) -> Project:
    """One track per ``(track id, media id)``, each with one clip of the whole file."""
    ms = tuple(media(m) for _, m in tracks)
    ts = tuple(Track(id=t, name=t, clips=(Clip(id=f"c{t}", media=m, start=0, offset=0,
                                               length=fr(60)),))
               for t, m in tracks)
    return Project(rate=RATE, media=ms, tracks=ts, sync_groups=tuple(groups))


EN = words(("So", 1.0, 1.3), ("um,", 1.4, 1.7), ("I", 1.8, 1.9), ("went", 1.9, 2.2),
           ("I", 2.4, 2.5), ("went", 2.5, 2.8), ("to", 2.8, 2.9), ("the", 2.9, 3.0),
           ("shop.", 3.0, 3.5),
           # a 3.0 s pause
           ("And", 6.5, 6.7), ("then", 6.7, 6.9), ("er", 7.0, 7.3), ("we", 7.4, 7.5),
           ("left.", 7.5, 8.0))

FI = words(("No", 1.0, 1.2), ("öö", 1.3, 1.8), ("siis", 1.9, 2.1), ("niinku", 2.2, 2.6),
           ("se", 2.7, 2.8), ("oli", 2.8, 3.0), ("hyvä.", 3.0, 3.4))


def by_kind(found, kind):
    return [c for c in found if c.kind == kind]


# -- detection ------------------------------------------------------------------


def test_the_filler_table_has_english_and_finnish():
    assert {"en", "fi"} <= set(cm.FILLERS)
    for word in ("Um,", "ööh", "Erm", "niinku"):
        assert cm.is_filler(word), word
    for word in ("went", "siis"):
        assert not cm.is_filler(word), word
    # Only the language's own table when the language is known.
    assert not cm.is_filler("niinku", "en")


def test_fillers_are_found_in_english_and_finnish():
    p = project(("a", "ma"), ("b", "mb"))
    found = cm.detect(p, {"ma": EN, "mb": FI})
    fillers = {(c.media, c.text) for c in by_kind(found, "filler")}
    assert fillers == {("ma", "um,"), ("ma", "er"), ("mb", "öö"), ("mb", "niinku")}
    um = next(c for c in found if c.text == "um,")
    assert (um.start, um.end) == (f(1.4), f(1.7))
    assert (um.scope, um.state) == ("track", "open")
    # A hesitation is a surer cut than a discourse word.
    oo = next(c for c in found if c.text == "öö")
    niinku = next(c for c in found if c.text == "niinku")
    assert oo.score > niinku.score


def test_a_repeated_phrase_is_a_retake_and_the_first_take_is_the_cut():
    p = project(("a", "ma"))
    found = cm.detect(p, {"ma": EN})
    [retake] = by_kind(found, "retake")
    # "I went I went": cut from the first "I" up to the second, keep the second.
    assert (retake.start, retake.end) == (f(1.8), f(2.4))
    assert retake.text == "I went"
    assert retake.scope == "track"


def test_a_repeat_too_far_apart_is_not_a_retake():
    w = words(("we", 1.0, 1.2), ("went", 1.2, 1.5), ("there", 1.5, 1.8),
              ("we", 9.0, 9.2), ("went", 9.2, 9.5))
    assert not by_kind(cm.detect(project(("a", "ma")), {"ma": w}), "retake")


def test_a_long_pause_is_a_candidate_that_leaves_a_natural_pause():
    p = project(("a", "ma"))
    [pause] = by_kind(cm.detect(p, {"ma": EN}), "silence")
    keep = cm.KEEP_PAUSE_S / 2
    assert (pause.start, pause.end) == (f(3.5 + keep), f(6.5 - keep))
    assert pause.reason["key"] == "candidate.reason.silence"


def test_short_pauses_and_the_silence_before_and_after_speech_are_not_candidates():
    w = words(("one", 5.0, 5.5), ("two", 6.4, 6.8))  # 0.9 s pause, 5 s of lead-in
    assert not by_kind(cm.detect(project(("a", "ma")), {"ma": w}), "silence")


def test_ids_are_stable_across_runs_and_differ_by_kind_and_range():
    p = project(("a", "ma"), ("b", "mb"))
    first = [c.id for c in cm.detect(p, {"ma": EN, "mb": FI})]
    again = [c.id for c in cm.detect(p, {"ma": EN, "mb": FI})]
    assert first == again
    assert len(set(first)) == len(first)
    assert cm.candidate_id("x" * 64, "filler", 1, 2) != cm.candidate_id("x" * 64,
                                                                         "filler", 1, 3)


def test_ids_survive_an_edit_that_moves_the_clip_and_the_placement_follows():
    p = project(("a", "ma"))
    before = {c.id: c for c in cm.detect(p, {"ma": EN})}
    moved = ops.move_clip(p, "ca", fr(10))
    after = {c.id: c for c in cm.detect(moved, {"ma": EN})}
    assert set(after) == set(before)
    um = next(c for c in after.values() if c.text == "um,")
    assert cm.spans(moved, um) == [(fr(11.4), fr(11.7))]
    assert cm.spans(p, um) == [(fr(1.4), fr(1.7))]


def test_ids_survive_an_earlier_ripple_cut():
    p = project(("a", "ma"))
    before = {c.id for c in cm.detect(p, {"ma": EN})}
    cut = ops.ripple_delete(p, fr(0.2), fr(0.6))
    assert {c.id for c in cm.detect(cut, {"ma": EN})} == before


def test_overlapping_candidates_merge_into_one():
    # "um um" right after each other: two fillers that touch become one.
    w = words(("a", 1.0, 1.2), ("um", 1.3, 1.6), ("um", 1.6, 1.9), ("b", 2.0, 2.2))
    found = cm.detect(project(("a", "ma")), {"ma": w})
    fillers = by_kind(found, "filler")
    assert len(fillers) == 1
    assert (fillers[0].start, fillers[0].end) == (f(1.3), f(1.9))


def test_merge_ranges_unions_overlaps_and_keeps_the_stronger_kind():
    a = cm.Candidate(id="", kind="filler", media="ma", start=10, end=20, score=0.9)
    b = cm.Candidate(id="", kind="retake", media="ma", start=15, end=30, score=0.6)
    c = cm.Candidate(id="", kind="filler", media="ma", start=40, end=50, score=0.9)
    p = project(("a", "ma"))
    merged = cm.merge_overlaps(p, [a, b, c])
    assert [(m.kind, m.start, m.end) for m in merged] == [("retake", 10, 30),
                                                          ("filler", 40, 50)]
    assert merged[0].id == cm.candidate_id(p.media_item("ma").sha256, "retake", 10, 30)


def test_stretches_already_muted_gated_or_cut_are_not_proposed():
    p = project(("a", "ma"))
    muted = ops.mute_range(p, fr(1.4), fr(1.7), ["a"])
    assert not [c for c in cm.detect(muted, {"ma": EN}) if c.text == "um,"]
    gated = ops.set_gate(p, "a", [(fr(1.3), fr(1.8))])
    assert not [c for c in cm.detect(gated, {"ma": EN}) if c.text == "um,"]
    cut = ops.ripple_delete(p, fr(1.35), fr(1.75))
    assert not [c for c in cm.detect(cut, {"ma": EN}) if c.text == "um,"]
    # The others are still there.
    assert [c for c in cm.detect(cut, {"ma": EN}) if c.text == "er"]


# -- sync groups --------------------------------------------------------------------


def grouped(origin_b: float = 0.0) -> Project:
    """Anna (ma) and Ville (mb) recorded together; Ville's file starts
    ``origin_b`` seconds later on the group clock and his clip sits there."""
    p = project(("a", "ma"), ("b", "mb"),
                groups=[SyncGroup(id="g1", main="ma",
                                  members=(("ma", 0), ("mb", f(origin_b))))])
    track_b = p.track("b")
    clip = replace(track_b.clips[0], start=fr(origin_b), length=fr(60 - origin_b))
    return ops._replace_track(p, replace(track_b, clips=(clip,)))


def test_a_pause_in_a_group_is_a_candidate_only_when_everyone_is_quiet():
    anna = words(("hello", 1.0, 1.5), ("there", 5.0, 5.5), ("bye", 9.0, 9.4))
    # Ville talks in Anna's first pause (on his own clock: 2 s later).
    ville = words(("yes", 1.0, 2.5), ("ok", 12.0, 12.3))
    p = grouped(origin_b=2.0)
    found = by_kind(cm.detect(p, {"ma": anna, "mb": ville}), "silence")
    keep = cm.KEEP_PAUSE_S / 2
    # Group clock: Anna 1.0-1.5, Ville 3.0-4.5, Anna 5.0-5.5, Anna 9.0-9.4,
    # Ville 14.0-14.3. Quiet runs: 1.5-3.0 (1.5 s), 4.5-5.0, 5.5-9.0, 9.4-14.0.
    assert [(c.start, c.end) for c in found] == [
        (f(1.5 + keep), f(3.0 - keep)), (f(5.5 + keep), f(9.0 - keep)),
        (f(9.4 + keep), f(14.0 - keep))]
    # Anchored to the group's main recording, applying to the whole group.
    assert {(c.media, c.scope) for c in found} == {("ma", "group")}


def test_a_group_pause_is_not_guessed_when_a_member_has_no_transcript():
    anna = words(("hello", 1.0, 1.5), ("there", 5.0, 5.5))
    p = grouped()
    assert not by_kind(cm.detect(p, {"ma": anna}), "silence")
    # Level data for Ville stands in for his transcript, and is intersected.
    quiet = {"mb": [(f(0.0), f(4.0))]}
    [pause] = by_kind(cm.detect(p, {"ma": anna}, silences=quiet), "silence")
    keep = cm.KEEP_PAUSE_S / 2
    assert (pause.start, pause.end) == (f(1.5 + keep), f(4.0 - keep))


def test_levels_tighten_a_transcript_pause():
    p = project(("a", "ma"))
    # The levels say the speaker breathed out until 4.2 s.
    quiet = {"ma": [(f(4.2), f(6.4))]}
    [pause] = by_kind(cm.detect(p, {"ma": EN}, silences=quiet), "silence")
    keep = cm.KEEP_PAUSE_S / 2
    assert (pause.start, pause.end) == (f(4.2 + keep), f(6.4 - keep))


def test_a_group_candidate_places_on_every_track_of_the_group():
    anna = words(("hello", 1.0, 1.5), ("there", 5.0, 5.5))
    ville = words(("hm", 0.2, 0.4), ("yes", 6.0, 6.5))
    p = grouped(origin_b=0.5)
    [pause] = by_kind(cm.detect(p, {"ma": anna, "mb": ville}), "silence")
    placed = cm.place(p, pause)
    assert {piece.track for piece in placed} == {"a", "b"}
    assert all((piece.start, piece.end) == cm.spans(p, pause)[0] for piece in placed)


# -- decisions --------------------------------------------------------------------


def detected(p, transcripts=None):
    return cm.detect(p, transcripts or {"ma": EN})


def test_merging_keeps_decisions_for_ids_that_persist():
    p = project(("a", "ma"))
    store, _ = cm.merge({}, detected(p), p)
    um = next(i for i, r in store.items() if r["text"] == "um,")
    er = next(i for i, r in store.items() if r["text"] == "er")
    store = cm.set_state(store, um, "kept")
    store = cm.set_state(store, er, "cut")
    again, changes = cm.merge(store, detected(p), p)
    assert (again[um]["state"], again[er]["state"]) == ("kept", "cut")
    assert changes == {"added": 0, "dropped": 0}
    assert again == store


def test_a_kept_candidate_is_not_proposed_again_even_slightly_moved():
    p = project(("a", "ma"))
    store, _ = cm.merge({}, detected(p), p)
    um = next(i for i, r in store.items() if r["text"] == "um,")
    store = cm.set_state(store, um, "kept")
    # A corrected transcript times the same word a little differently.
    shifted = [dict(w, s=w["s"] + f(0.05)) if w["w"] == "um," else w for w in EN]
    again, _ = cm.merge(store, cm.detect(p, {"ma": shifted}), p)
    ums = [r for r in again.values() if r["text"] == "um,"]
    assert [r["state"] for r in ums] == ["kept"]


def test_open_candidates_that_are_no_longer_found_are_dropped_marks_are_kept():
    p = project(("a", "ma"))
    store, _ = cm.merge({}, detected(p), p)
    mark = cm.mark(p, fr(20), fr(21), "a")
    store = {**store, mark.id: mark.record()}
    fewer = [w for w in EN if w["w"] != "er"]
    again, changes = cm.merge(store, cm.detect(p, {"ma": fewer}), p)
    assert not [r for r in again.values() if r["text"] == "er"]
    assert mark.id in again
    assert changes["dropped"] == 1


def test_the_store_is_bounded():
    p = project(("a", "ma"))
    many = [cm.Candidate(id=cm.candidate_id("x", "filler", i * 100, i * 100 + 50),
                         kind="filler", media="ma", start=i * 100, end=i * 100 + 50,
                         score=0.0 if i < 50 else 0.5)
            for i in range(cm.MAX_CANDIDATES + 50)]
    store, _ = cm.merge({}, many, p)
    assert len(store) == cm.MAX_CANDIDATES
    # The weakest open ones go first.
    assert min(r["score"] for r in store.values()) > 0.0


def test_unknown_keys_of_a_record_are_preserved():
    rec = {"kind": "filler", "media": "ma", "start": 1, "end": 2, "scope": "track",
           "state": "open", "score": 0.9, "reason": {"key": "candidate.reason.filler",
                                                     "params": {"word": "um"}},
           "text": "um", "future": {"x": 1}}
    c = cm.Candidate.from_record("k1", rec)
    assert c.record()["future"] == {"x": 1}
    assert cm.set_state({"k1": rec}, "k1", "kept")["k1"]["future"] == {"x": 1}


def test_a_bad_state_or_id_is_refused():
    with pytest.raises(cm.CandidateError):
        cm.set_state({}, "nope", "kept")
    rec = cm.mark(project(("a", "ma")), 0, 100, "a").record()
    with pytest.raises(cm.CandidateError):
        cm.set_state({"k": rec}, "k", "maybe")


# -- marking ------------------------------------------------------------------------


def test_a_mark_on_a_lone_clip_anchors_to_its_media():
    p = ops.move_clip(project(("a", "ma")), "ca", fr(10))
    m = cm.mark(p, fr(12), fr(13), "a")
    assert (m.kind, m.media, m.scope) == ("marked", "ma", "track")
    assert (m.start, m.end) == (f(2), f(3))
    assert cm.spans(p, m) == [(fr(12), fr(13))]


def test_a_mark_in_a_sync_group_anchors_to_the_group_clock():
    p = grouped(origin_b=2.0)
    m = cm.mark(p, fr(5), fr(6), "b")
    # Ville's clip plays his second 3 at timeline 5: group clock 5 = Anna's 5.
    assert (m.media, m.scope) == ("ma", "group")
    assert (m.start, m.end) == (f(5), f(6))
    assert {piece.track for piece in cm.place(p, m)} == {"a", "b"}


def test_a_mark_where_no_clip_plays_is_refused():
    with pytest.raises(cm.CandidateError):
        cm.mark(project(("a", "ma")), fr(70), fr(71), "a")
    with pytest.raises(ops.EditError):
        cm.mark(project(("a", "ma")), fr(2), fr(2), "a")


# -- applying -----------------------------------------------------------------------


def two_speakers() -> tuple[Project, dict]:
    return project(("a", "ma"), ("b", "mb")), {"ma": EN, "mb": FI}


def test_a_soft_cut_mutes_the_speakers_own_track_and_moves_nothing():
    p, tr = two_speakers()
    um = next(c for c in cm.detect(p, tr) if c.text == "um,")
    plan = cm.apply_plan(p, um)
    assert plan.mode == "soft"
    assert plan.tracks == ("a",)
    assert plan.spans == ((fr(1.4), fr(1.7)),)
    a = plan.project.track("a")
    muted = [(c.start, c.end) for c in a.clips if c.muted]
    assert muted == [(fr(1.4), fr(1.7))]
    assert plan.project.track("b") == p.track("b")
    assert plan.project.length == p.length
    assert plan.preview["skip"] == [[fr(1.4), fr(1.7)]]
    assert plan.preview["from"] == max(0, fr(1.4) - fr(cm.PREVIEW_PAD_S))
    assert plan.preview["to"] == fr(1.7) + fr(cm.PREVIEW_PAD_S)


def test_a_group_silence_soft_cuts_every_track_of_the_group():
    anna = words(("hello", 1.0, 1.5), ("there", 5.0, 5.5))
    ville = words(("hm", 0.2, 0.4), ("yes", 6.0, 6.5))
    p = grouped()
    [pause] = by_kind(cm.detect(p, {"ma": anna, "mb": ville}), "silence")
    plan = cm.apply_plan(p, pause)
    assert set(plan.tracks) == {"a", "b"}
    for tid in ("a", "b"):
        assert any(c.muted for c in plan.project.track(tid).clips)


def test_explicit_tracks_override_the_default():
    p, tr = two_speakers()
    um = next(c for c in cm.detect(p, tr) if c.text == "um,")
    plan = cm.apply_plan(p, um, tracks=["a", "b"])
    assert set(plan.tracks) == {"a", "b"}


def test_a_ripple_cut_closes_the_gap_and_keeps_the_group_together():
    anna = words(("hello", 1.0, 1.5), ("there", 5.0, 5.5))
    ville = words(("hm", 0.2, 0.4), ("yes", 6.0, 6.5))
    p = grouped()
    [pause] = by_kind(cm.detect(p, {"ma": anna, "mb": ville}), "silence")
    a, b = cm.spans(p, pause)[0]
    plan = cm.apply_plan(p, pause, mode="ripple")
    assert plan.mode == "ripple"
    for tid in ("a", "b"):
        assert plan.project.track(tid).clips[-1].end == fr(60) - (b - a)
    # Afterwards the candidate's audio is gone from the timeline.
    assert cm.spans(plan.project, pause) == []


def test_a_ripple_cut_of_a_lone_filler_cuts_every_track_outside_groups():
    p, tr = two_speakers()
    um = next(c for c in cm.detect(p, tr) if c.text == "um,")
    plan = cm.apply_plan(p, um, mode="ripple")
    # WP19a: tracks in no group follow the old rule, all tracks, so they stay in step.
    assert set(plan.tracks) == {"a", "b"}


def test_a_candidate_whose_audio_is_gone_cannot_be_applied():
    p, tr = two_speakers()
    um = next(c for c in cm.detect(p, tr) if c.text == "um,")
    gone = ops.ripple_delete(p, fr(1.0), fr(2.0))
    with pytest.raises(cm.CandidateError):
        cm.apply_plan(gone, um)
    with pytest.raises(cm.CandidateError):
        cm.apply_plan(p, um, mode="sideways")


def test_flicks_and_frames_agree_for_placement():
    p = project(("a", "ma"))
    c = cm.Candidate(id="x", kind="marked", media="ma",
                     start=frames_to_flicks(4800, RATE), end=frames_to_flicks(9600, RATE))
    assert cm.spans(p, c) == [(4800, 9600)]


def test_summary_counts_states():
    recs = {"1": {"state": "open"}, "2": {"state": "cut"}, "3": {"state": "kept"},
            "4": {"state": "open"}}
    assert cm.summary(recs) == {"open": 2, "cut": 1, "kept": 1, "total": 4}


def test_listing_a_full_store_over_a_heavily_cut_hour_is_quick():
    """Ground rule 14: the list is read on every panel refresh. Measured
    20 ms here (1,000 candidates, 1,204 clips); the bound leaves 25 times that."""
    hour = 3600
    ms = tuple(media(f"m{i}", hour) for i in range(4))
    ts = tuple(Track(id=f"t{i}", name="t", clips=(Clip(id=f"c{i}", media=f"m{i}",
                                                       start=0, offset=0,
                                                       length=fr(hour)),))
               for i in range(4))
    p = Project(rate=RATE, media=ms, tracks=ts, sync_groups=(
        SyncGroup(id="g", main="m0", members=tuple((f"m{i}", 0) for i in range(4))),))
    for k in range(300):
        p = ops.ripple_delete(p, fr(3000 - k * 10), fr(3000 - k * 10 + 0.5))
    found = [cm.Candidate(id=str(i), kind="filler", media=f"m{i % 4}",
                          start=f(i * 3.0), end=f(i * 3.0 + 0.4))
             for i in range(cm.MAX_CANDIDATES)]
    began = time.perf_counter()
    index = cm.ClipIndex(p)
    rows = [cm.view(p, c, index) for c in found]
    assert time.perf_counter() - began < 0.5
    assert len(rows) == cm.MAX_CANDIDATES
