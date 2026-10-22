"""Searching every transcript of the project for words the edit does not play (T64).

The Transcript shows only what is heard, so material that was cut, muted, gated or
never placed is found here, with the reason it is not in the edit.
"""

from kuulas import material_search
from kuulas.clock import FLICKS
from kuulas.model import Clip, Media, Project, Track

RATE = 48_000
SECOND = RATE


def word(text, start, end, spk=""):
    return {"w": text, "s": round(start * FLICKS), "e": round(end * FLICKS), "spk": spk}


# "joo siis se oli ihan sattumaa et": one word per second, from 1 s.
WORDS = [word(t, i + 1, i + 1.5) for i, t in
         enumerate(["joo", "siis", "se", "oli", "ihan", "sattumaa", "et"])]


def project(clips=(), *, gate=(), mute=False, media=("m",)):
    track = Track("t", "Voice", kind="speech", clips=tuple(clips), gate=tuple(gate),
                  mute=mute)
    return Project(
        rate=RATE,
        media=tuple(Media(m, f"{m}.wav", 1, 20 * SECOND, sha256=m * 64) for m in media),
        tracks=(track,))


def hits(p, query, words=WORDS):
    return material_search.search(p, {"m": words}, query)


def test_a_word_the_edit_plays_is_not_a_removed_hit():
    p = project([Clip("c", "m", 0, 0, 20 * SECOND)])
    assert hits(p, "sattumaa") == []


def test_a_word_in_a_removed_stretch_is_cut():
    # The clip keeps only the first 5 seconds: "sattumaa" at 6 s was cut away.
    p = project([Clip("c", "m", 0, 0, 5 * SECOND)])
    [hit] = hits(p, "sattumaa")
    assert hit["status"] == "cut"
    assert hit["media"] == "m"
    assert (hit["first"], hit["last"]) == (5, 5)
    assert hit["start"] == round(6 * FLICKS)
    assert hit["end"] == round(6.5 * FLICKS)


def test_a_word_under_a_muted_clip_is_muted():
    p = project([Clip("c", "m", 0, 0, 20 * SECOND, muted=True)])
    [hit] = hits(p, "sattumaa")
    assert hit["status"] == "muted"


def test_a_word_on_a_muted_track_is_muted():
    p = project([Clip("c", "m", 0, 0, 20 * SECOND)], mute=True)
    [hit] = hits(p, "sattumaa")
    assert hit["status"] == "muted"


def test_a_word_under_a_closed_gate_is_gated():
    # The mic is shut from 5.5 s to 7 s; "sattumaa" is at 6 s.
    shut = [(round(5.5 * SECOND), 7 * SECOND)]
    p = project([Clip("c", "m", 0, 0, 20 * SECOND)], gate=shut)
    [hit] = hits(p, "sattumaa")
    assert hit["status"] == "gated"


def test_a_recording_placed_nowhere_is_unused():
    p = project([])
    [hit] = hits(p, "sattumaa")
    assert hit["status"] == "unused"


def test_another_clip_that_plays_the_word_keeps_it_in_the_edit():
    p = project([Clip("a", "m", 0, 0, 20 * SECOND, muted=True),
                 Clip("b", "m", 30 * SECOND, 0, 20 * SECOND)])
    assert hits(p, "sattumaa") == []


def test_a_phrase_that_is_only_partly_played_is_a_removed_hit():
    # "ihan" (5 s) is kept, "sattumaa" (6 s) is cut.
    p = project([Clip("c", "m", 0, 0, round(5.9 * SECOND))])
    [hit] = hits(p, "ihan sattumaa")
    assert hit["status"] == "cut"
    assert hit["partly"] is True
    assert (hit["first"], hit["last"]) == (4, 5)


def test_a_phrase_with_nothing_played_is_not_partly():
    p = project([Clip("c", "m", 0, 0, 2 * SECOND)])
    [hit] = hits(p, "ihan sattumaa")
    assert hit["partly"] is False


def test_the_hit_carries_its_context_for_the_list():
    p = project([Clip("c", "m", 0, 0, 2 * SECOND)])
    [hit] = hits(p, "sattumaa")
    assert hit["before"] == "siis se oli ihan"
    assert hit["match"] == "sattumaa"
    assert hit["after"] == "et"


def test_the_context_is_limited_to_a_few_words_each_side():
    words = [word(f"w{i}", i, i + 0.5) for i in range(30)]
    p = project([Clip("c", "m", 0, 0, 2 * SECOND)])
    [hit] = material_search.search(p, {"m": words}, "w15")
    assert hit["before"] == "w11 w12 w13 w14"
    assert hit["after"] == "w16 w17 w18 w19"


def test_the_speaker_label_is_kept():
    words = [word("hei", 1, 1.5, spk="Anna"), word("sattumaa", 2, 2.5, spk="Anna")]
    p = project([])
    [hit] = material_search.search(p, {"m": words}, "sattumaa")
    assert hit["spk"] == "Anna"


def test_matching_is_by_prefix_without_accents_like_the_transcript_find():
    words = [word("Sattumalta", 1, 1.5)]
    p = project([])
    assert len(material_search.search(p, {"m": words}, "SATTUMA")) == 1
    assert material_search.search(p, {"m": words}, "s") == []
    assert material_search.search(p, {"m": words}, "") == []


def test_every_recording_with_a_transcript_is_searched_in_time_order_of_media():
    p = project([], media=("m", "n"))
    other = [word("sattumaa", 3, 3.5)]
    found = material_search.search(p, {"m": WORDS, "n": other}, "sattumaa")
    assert [h["media"] for h in found] == ["m", "n"]


def test_a_transcript_of_an_unknown_recording_is_skipped():
    p = project([])
    assert material_search.search(p, {"gone": WORDS}, "sattumaa") == []


def test_an_excerpt_is_judged_on_its_original_recordings_clock():
    # "n" is a copy of "m" from 4 s on. "m" is played only for its first 5 s, so the
    # excerpt's word at 2 s (= 6 s of "m") is outside what the edit plays.
    p = project([Clip("c", "m", 0, 0, 5 * SECOND)], media=("m",))
    excerpt = Media("n", "n.wav", 1, 10 * SECOND, sha256="n" * 64,
                    excerpt_of="m", excerpt_start_flicks=round(4 * FLICKS))
    p = Project(rate=RATE, media=(*p.media, excerpt), tracks=p.tracks)
    [hit] = material_search.search(p, {"n": [word("sattumaa", 2, 2.5)]}, "sattumaa")
    assert hit["status"] == "cut"
