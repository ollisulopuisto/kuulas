"""Which words come back with a hit: the sentence, kept inside what was removed (T64).

Owner, 2026-10-21: what comes back is what is selected; with no selection it falls back
to the hit's sentence. The stretch is padded to the middle of the pauses (as a cut is)
and never reaches into audio the edit still plays, so nothing is heard twice.
"""

from kuulas import put_back
from kuulas.clock import FLICKS
from kuulas.model import Clip, Media, Project, Track

RATE = 48_000
SECOND = RATE


def word(text, start, end, spk=""):
    return {"w": text, "s": round(start * FLICKS), "e": round(end * FLICKS), "spk": spk}


def flicks(seconds):
    return round(seconds * FLICKS)


def project(clips=(), length=600):
    track = Track("t", "Voice", kind="speech", clips=tuple(clips))
    return Project(rate=RATE, media=(Media("m", "m.wav", 1, length * SECOND,
                                           sha256="m" * 64),), tracks=(track,))


def say(text, start, gap=0.2):
    """Words of ``text`` half a second long, ``gap`` apart, from ``start`` seconds."""
    out, at = [], start
    for token in text.split():
        out.append(word(token, at, at + 0.5))
        at += 0.5 + gap
    return out


def choose(p, words, first, last=None):
    return put_back.choose_range(p, "m", words, first, first if last is None else last)


def test_the_sentence_runs_from_the_last_full_stop_to_the_next():
    words = say("joo. siis se oli ihan sattumaa. et", 1)
    start, end = choose(project(), words, 5)  # "sattumaa."
    # From the pause midpoint before "siis" to the pause midpoint after "sattumaa.".
    assert start == (words[0]["e"] + words[1]["s"]) // 2
    assert end == (words[5]["e"] + words[6]["s"]) // 2


def test_a_long_pause_ends_a_sentence_without_punctuation():
    words = say("hei kaikki", 1) + say("tama jatkuu", 5) + say("viela", 7.5)
    start, end = choose(project(), words, 3)  # "jatkuu"
    assert start == (words[1]["e"] + words[2]["s"]) // 2
    assert end == (words[3]["e"] + words[4]["s"]) // 2


def test_a_change_of_speaker_ends_a_sentence():
    words = [word("kerro", 1, 1.5, "Anna"), word("sattumaa", 1.7, 2.2, "Ville"),
             word("kylla", 2.4, 2.9, "Ville")]
    start, end = choose(project(), words, 1)
    assert start == (words[0]["e"] + words[1]["s"]) // 2
    assert end == words[2]["e"]


def test_the_first_and_last_word_of_a_recording_have_no_pad():
    words = say("vain nama", 1)
    start, end = choose(project(), words, 0, 1)
    assert (start, end) == (words[0]["s"], words[1]["e"])


def test_it_never_reaches_into_audio_the_edit_still_plays():
    # The edit plays only the first 3 s of the recording; the words after that are cut.
    words = say("ensin tama sitten sattumaa", 1, gap=0.2)
    p = project([Clip("c", "m", 0, 0, 3 * SECOND)])
    start, _end = choose(p, words, 3)
    assert start >= flicks(3)


def test_a_sliver_left_over_comes_back_with_it():
    # Removed block 3 s .. 20 s; the sentence 10-12 s leaves more than a second either
    # side, so only the sentence returns. One at 3.5-5 s leaves a 0.5 s sliver: the whole
    # block's start is taken.
    p = project([Clip("c", "m", 0, 0, 3 * SECOND),
                 Clip("d", "m", 20 * SECOND, 20 * SECOND, 5 * SECOND)])
    far = [word("kaukana", 10, 10.5), word("sana.", 10.7, 11.2)]
    assert choose(p, far, 1)[0] > flicks(3.5)
    near = [word("lahella", 3.5, 4.0), word("sana.", 4.2, 4.7)]
    assert choose(p, near, 1)[0] == flicks(3)


def test_a_sentence_that_is_most_of_the_block_takes_the_whole_block():
    p = project([Clip("c", "m", 0, 0, 3 * SECOND),
                 Clip("d", "m", 10 * SECOND, 10 * SECOND, 5 * SECOND)])
    words = say("pitka lause joka vie lahes koko poistetun osan.", 3.5, gap=0.1)
    assert choose(p, words, len(words) - 1) == (flicks(3), flicks(10))


def test_a_recording_placed_nowhere_never_comes_back_whole():
    words = say("pieni lause.", 100)
    start, end = choose(project(), words, 1)
    assert (start, end) != (0, flicks(600))
    assert start > 0


def test_the_sentence_stops_at_a_word_the_edit_still_plays():
    # "keski" (3.1-3.6 s) is played; the cut words on both sides are separate blocks.
    words = [word("ennen", 2.4, 2.9), word("keski", 3.1, 3.55), word("jalkeen", 3.7, 4.2)]
    p = project([Clip("c", "m", 3 * SECOND, 3 * SECOND, round(0.6 * SECOND))])
    start, end = choose(p, words, 2)
    assert start >= flicks(3.6)
    start, end = choose(p, words, 0)
    assert end <= flicks(3.0)
