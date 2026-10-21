"""Auto-Silence values learned from the selection (``silence_learn``): Kuulas' clips
as the shared ``silencelearn`` package's examples, levels from Kuulas' own level
measurement, and the learned threshold as the panel's options."""

from dataclasses import replace

import numpy as np
import pytest
import silencelearn as sl
from gate_fixtures import RATE, MemoryStore

from kuulas import analysis, levels, ops, silence_learn
from kuulas.model import Media, Project
from kuulas.silence_options import RANGES, SilenceOptions

NOISE_AMP = 0.001  # -60 dBFS RMS
SPEECH_AMP = 0.3


def _db(x):
    return 10 * np.log10(np.mean(np.square(x)))


def recording(noise_s=10.0, speech_s=10.0, seed=1):
    """One file: ``noise_s`` of room noise, then ``speech_s`` of talk: half a second
    of loud speech, half a second of pause (the room noise), as people talk."""
    rng = np.random.default_rng(seed)
    noise = NOISE_AMP * rng.standard_normal(int((noise_s + speech_s) * RATE))
    t = np.arange(int(speech_s * RATE)) / RATE
    talking = (t % 1.0) < 0.5
    talk = (SPEECH_AMP * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))
            * rng.standard_normal(t.size))
    noise[int(noise_s * RATE):] += np.where(talking, talk, 0.0)
    return noise.astype(np.float32)[None, :]


def project(noise_s=10.0, speech_s=10.0, mute_s=None, *, mute_speech=False):
    """Track T0 holds the file as two clips, placed later on the timeline than in the
    file (start != offset, so file time must come from the offset): ``cm`` over the
    first ``mute_s`` seconds of noise (muted), ``cs`` over the talk (open)."""
    audio = recording(noise_s, speech_s)
    store = MemoryStore({"m0": audio})
    n = audio.shape[1]
    p = Project(rate=RATE)
    p = ops.add_media(p, Media(id="m0", name="a.wav", channels=1, frames=n,
                               sha256="a" * 64))
    p = ops.add_track(p, track_id="T0", name="Anna")
    mute_frames = int((noise_s if mute_s is None else mute_s) * RATE)
    p = ops.add_clip(p, "T0", "m0", start=5 * RATE, offset=0, length=mute_frames,
                     clip_id="cm")
    speech_at = int(noise_s * RATE)
    p = ops.add_clip(p, "T0", "m0", start=5 * RATE + speech_at, offset=speech_at,
                     clip_id="cs")
    p = ops.set_clip(p, "cs" if mute_speech else "cm", muted=True)
    return p, store


# -- the examples ----------------------------------------------------------------------


def test_selected_clips_become_examples_in_the_files_own_seconds():
    p, _ = project()
    got = silence_learn.examples(p, ["cm", "cs"])
    assert got == {"T0": [sl.Clip("m0", 0.0, 10.0, muted=True),
                          sl.Clip("m0", 10.0, 20.0, muted=False)]}


def test_unselected_unknown_and_music_clips_are_not_examples():
    p, _ = project()
    p = ops.add_track(p, track_id="M", name="Music", kind="music")
    p = ops.add_clip(p, "M", "m0", clip_id="music")
    assert silence_learn.examples(p, ["cm", "music", "nope"]) == {
        "T0": [sl.Clip("m0", 0.0, 10.0, muted=True)]}


def test_an_ungated_clip_keeps_its_role_muted_or_not():
    p, _ = project()
    p = replace(p, tracks=tuple(
        replace(t, clips=tuple(replace(c, ungated=c.id == "cm") for c in t.clips))
        for t in p.tracks))
    got = silence_learn.examples(p, ["cm", "cs"])["T0"]
    assert [c.muted for c in got] == [True, False]


# -- the levels ------------------------------------------------------------------------


def test_a_level_is_the_mean_square_of_the_window_in_dbfs():
    p, store = project()
    lv = silence_learn.MediaLevels(p, store)
    window = store.arrays["m0"][0, 2 * RATE:int(2.3 * RATE)]
    assert lv.level("m0", 2.0, 2.3) == pytest.approx(_db(window), abs=0.01)
    assert lv.missing() is False


def test_the_level_from_the_cached_envelope_is_the_same_as_from_the_audio():
    p, store = project()

    class Enveloped(MemoryStore):
        def envelope(self, media_id, block):
            a = self.arrays[media_id]
            return levels.block_energy(lambda f, c: self.read(media_id, f, c),
                                       a.shape[1], block)

    from_audio = silence_learn.MediaLevels(p, store)
    from_env = silence_learn.MediaLevels(p, Enveloped(store.arrays))
    for a, b in [(0.0, 0.3), (2.01, 2.31), (10.5, 10.8)]:
        assert from_env.level("m0", a, b) == pytest.approx(from_audio.level("m0", a, b),
                                                           abs=0.1)


def test_a_window_outside_the_file_has_no_level_and_one_past_its_end_is_cut():
    p, store = project()
    lv = silence_learn.MediaLevels(p, store)
    assert lv.level("m0", 25.0, 25.3) is None
    tail = store.arrays["m0"][0, int(19.9 * RATE):]
    assert lv.level("m0", 19.9, 20.2) == pytest.approx(_db(tail), abs=0.01)


def test_a_missing_file_has_no_level_and_says_so():
    p, store = project()

    class Gone(MemoryStore):
        def missing(self):
            return ["m0"]

    lv = silence_learn.MediaLevels(p, Gone(store.arrays))
    assert lv.level("m0", 0.0, 0.3) is None
    assert lv.missing() is True


def test_the_levels_read_only_the_windows_never_a_whole_file():
    p, store = project(noise_s=60.0)
    reads = []

    class Spy(MemoryStore):
        def read(self, media_id, first, count):
            reads.append(count)
            return super().read(media_id, first, count)

    silence_learn.calibrate_tracks(p, Spy(store.arrays), ["cm", "cs"])
    assert reads
    assert max(reads) <= int(sl.WINDOW * RATE) + 1


# -- learning per track ----------------------------------------------------------------


def test_the_threshold_is_learned_just_above_the_muted_noise():
    p, store = project()
    got = silence_learn.calibrate_tracks(p, store, ["cm", "cs"])["T0"]
    assert got["code"] == "learned"
    assert got["threshold"] == pytest.approx(-60.0 + sl.MARGIN_DB, abs=1.5)
    assert got["muted_seconds"] == pytest.approx(10.0)
    assert got["kept_share"] > 0.5


@pytest.mark.parametrize(("case", "code"), [
    ("too_little", "too_little"), ("no_muted", "no_muted"),
    ("speech_guard", "speech_guard"), ("missing", "no_audio")])
def test_a_refusal_has_a_code_the_ui_can_translate(case, code):
    p, store = project(mute_s=2.0 if case == "too_little" else None,
                       mute_speech=case == "speech_guard")
    ids = ["cm", "cs"]
    if case == "no_muted":
        p = ops.set_clip(p, "cm", muted=False)
    if case == "speech_guard":
        # The talk muted and only a little noise left open: the "muted" level is talk.
        p = ops.set_clip(p, "cm", muted=False)
    if case == "missing":
        class Gone(MemoryStore):
            def missing(self):
                return ["m0"]
        store = Gone(store.arrays)
    got = silence_learn.calibrate_tracks(p, store, ids)["T0"]
    assert got["code"] == code
    assert got["threshold"] is None
    if code == "too_little":
        assert got["args"] == {"seconds": 2.0, "min": sl.MIN_SECONDS}


# -- the options -----------------------------------------------------------------------


def _learn(p, store, ids, options=None):
    measure = analysis.measure_silence(p, store)
    floors = {tid: lv.floor for tid, lv in measure.levels.items()}
    cals = silence_learn.calibrate_tracks(p, store, ids)
    return silence_learn.suggestion(p, cals, floors, options or SilenceOptions()), floors


def test_the_learned_threshold_becomes_the_margin_over_the_tracks_floor():
    p, store = project(noise_s=30.0, speech_s=20.0)
    got, floors = _learn(p, store, ["cm", "cs"], SilenceOptions(dominance_db=9.0))
    row = got["tracks"][0]
    assert row["track_id"] == "T0"
    assert row["margin_db"] == pytest.approx(row["threshold"] - floors["T0"], abs=0.01)
    low, high = RANGES["margin_db"]
    want = min(high, max(low, row["margin_db"]))
    assert got["options"]["margin_db"] == pytest.approx(want, abs=0.05)
    # What the clips cannot teach stays as it was.
    assert got["options"]["dominance_db"] == 9.0
    assert got["learned"] is True


def test_several_tracks_take_the_gentlest_margin():
    """One margin for all mics: the smallest learned one, because closing too much is
    the worse error (silencelearn's rule)."""
    rows = [{"track_id": "a", "code": "learned", "margin_db": 8.0},
            {"track_id": "b", "code": "learned", "margin_db": 5.5},
            {"track_id": "c", "code": "too_little", "margin_db": None}]
    assert silence_learn.combined_margin(rows) == 5.5
    assert silence_learn.combined_margin(rows[2:]) is None


def test_a_margin_outside_the_sliders_range_is_clamped_and_said():
    p, store = project()
    cals = silence_learn.calibrate_tracks(p, store, ["cm", "cs"])
    got = silence_learn.suggestion(p, cals, {"T0": cals["T0"]["threshold"] - 40.0},
                                   SilenceOptions())
    assert got["options"]["margin_db"] == RANGES["margin_db"][1]
    assert got["clamped"] is True


def test_nothing_learned_leaves_the_options_as_they_were_and_says_why():
    p, store = project(mute_s=2.0)
    got, _ = _learn(p, store, ["cm", "cs"], SilenceOptions(margin_db=7.0))
    assert got["learned"] is False
    assert got["options"]["margin_db"] == 7.0
    assert got["tracks"][0]["code"] == "too_little"


def test_a_track_that_is_not_measured_is_refused_not_skipped():
    p, store = project()
    p = replace(p, tracks=tuple(replace(t, mute=True) for t in p.tracks))
    cals = silence_learn.calibrate_tracks(p, store, ["cm", "cs"])
    got = silence_learn.suggestion(p, cals, {}, SilenceOptions())
    assert got["tracks"][0]["code"] == "not_measured"
    assert got["learned"] is False
