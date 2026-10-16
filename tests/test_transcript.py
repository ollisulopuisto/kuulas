import copy

from kuulas import ops, transcript
from kuulas.clock import FLICKS
from kuulas.model import Media, Project

R = 1000


def words(*items):
    """Stored words: flicks from the media's start (docs/FORMAT.md)."""
    return [{"w": w, "s": round(s * FLICKS), "e": round(e * FLICKS), "spk": "A"}
            for w, s, e in items]


def project():
    p = Project(rate=R)
    p = ops.add_media(p, Media(id="m", name="a.wav", channels=1, frames=10 * R))
    p = ops.add_track(p, track_id="t", name="A")
    return ops.add_clip(p, track_id="t", media_id="m", clip_id="c")


WORDS = {"m": words(("hei", 0, 0.5), ("tämä", 1.0, 1.5), ("on", 2.0, 2.5))}


def test_words_land_on_the_timeline_where_their_clip_plays_them():
    p = ops.move_clip(project(), "c", start=3 * R)
    tw = transcript.timeline_words(p, WORDS)
    assert [(w["w"], w["s"]) for w in tw] == [("hei", 3000), ("tämä", 4000), ("on", 5000)]


def test_deleting_a_word_cuts_to_the_middle_of_the_pauses():
    tw = transcript.timeline_words(project(), WORDS)
    assert transcript.cut_range(tw, [1]) == (750, 1750)


def test_cut_at_the_edges_takes_the_word_itself():
    tw = transcript.timeline_words(project(), WORDS)
    assert transcript.cut_range(tw, [0]) == (0, 750)
    assert transcript.cut_range(tw, [2]) == (1750, 2500)


def test_audio_edit_moves_the_transcript_with_it():
    p = project()
    tw = transcript.timeline_words(p, WORDS)
    a, b = transcript.cut_range(tw, [1])
    p = ops.ripple_delete(p, a, b)
    after = transcript.timeline_words(p, WORDS)
    assert [w["w"] for w in after] == ["hei", "on"]
    assert after[1]["s"] == 1000


def test_words_under_muted_pieces_are_marked():
    p = ops.mute_ranges(project(), "t", [(900, 1600)])
    tw = transcript.timeline_words(p, WORDS)
    assert [w["muted"] for w in tw] == [False, True, False]


def test_trimmed_away_words_disappear():
    p = ops.trim_clip(project(), "c", end=1200)
    assert [w["w"] for w in transcript.timeline_words(p, WORDS)] == ["hei"]


def test_rate_change_leaves_words_untouched():
    # The same recording in a 44.1 kHz and a 48 kHz project (WP27 converts
    # edit state only): the stored words are not touched, and land on the
    # same moments at either rate.
    stored = {"m": words(("hei", 0.5, 1.0), ("moi", 2.25, 2.75))}
    before = copy.deepcopy(stored)
    for rate in (44100, 48000, 8000):
        p = Project(rate=rate)
        p = ops.add_media(p, Media(id="m", name="a.wav", channels=1, frames=10 * rate))
        p = ops.add_track(p, track_id="t", name="A")
        p = ops.add_clip(p, track_id="t", media_id="m", clip_id="c", start=rate)
        tw = transcript.timeline_words(p, stored)
        assert [(w["s"], w["e"]) for w in tw] == [
            (rate + rate // 2, 2 * rate), (rate + 9 * rate // 4, rate + 11 * rate // 4)]
    assert stored == before
