"""Subtitles from timeline words: grouping, cue times, SRT and VTT text.

The word dicts are exactly what ``transcript.timeline_words`` returns:
``s``/``e`` in frames at the project rate (48 000 here), ``spk``/``person``
for the speaker, ``muted`` for words no clip plays audibly.
"""

from kuulas.clock import frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.subtitles import Cue, cues, to_srt, to_vtt
from kuulas.transcript import timeline_words

RATE = 48_000


def word(text: str, s: int, e: int, *, track: str = "ta", spk: str = "",
         person: str = "", muted: bool = False) -> dict:
    """A word dict exactly as ``timeline_words`` gives it (frames at RATE)."""
    return {"w": text, "spk": spk, "person": person, "s": s, "e": e,
            "track": track, "clip": "ca", "media": "ma", "index": 0,
            "muted": muted}


# -- grouping ----------------------------------------------------------------


def test_a_speaker_change_starts_a_new_cue():
    result = cues([
        word("moi", 0, 24_000, spk="A"),
        word("hei", 24_000, 48_000, spk="A"),
        word("taas", 48_000, 72_000, spk="B"),
    ])
    assert result == (
        Cue(0.0, 1.0, ("moi hei",), "A"),
        Cue(1.0, 1.5, ("taas",), "B"),
    )


def test_a_track_change_starts_a_new_cue():
    # Same speaker, no gap break (0.5 s <= 1.0 s): only the track splits.
    result = cues([
        word("moi", 0, 24_000, spk="A", track="ta"),
        word("hei", 48_000, 72_000, spk="A", track="tb"),
    ])
    assert result == (
        Cue(0.0, 0.5, ("moi",), "A"),
        Cue(1.0, 1.5, ("hei",), "A"),
    )


def test_a_gap_over_gap_seconds_starts_a_new_cue():
    # Exactly gap_seconds (48 000 frames) is not over it: one cue.
    tight = cues([word("moi", 0, 24_000), word("hei", 72_000, 96_000)])
    assert tight == (Cue(0.0, 2.0, ("moi hei",), ""),)
    # One frame more splits it, and the short first cue is stretched.
    split = cues([word("moi", 0, 24_000), word("hei", 72_001, 168_000)])
    assert split == (Cue(0.0, 0.5, ("moi",), ""),
                     Cue(72_001 / RATE, 3.5, ("hei",), ""))


def test_text_over_max_chars_times_max_lines_starts_a_new_cue():
    # 5 * 2 = 10 characters: "abc de" fits, " fghi" would exceed.
    result = cues([word("abc", 0, 24_000), word("de", 24_000, 48_000),
                   word("fghi", 48_000, 72_000)], max_chars=5, max_lines=2)
    assert result == (Cue(0.0, 1.0, ("abc", "de"), ""),
                      Cue(1.0, 1.5, ("fghi",), ""))
    # Exactly 10 characters stays one cue, wrapped to the 5-character lines.
    exact = cues([word("abcde", 0, 24_000), word("fghi", 24_000, 48_000)],
                 max_chars=5, max_lines=2)
    assert exact == (Cue(0.0, 1.0, ("abcde", "fghi"), ""),)


def test_a_word_over_max_seconds_starts_a_new_cue():
    # "kolme" would run the cue to 2.5 s > 2.0 s, so it starts a new cue.
    result = cues([word("yksi", 0, 24_000), word("kaksi", 24_000, 48_000),
                   word("kolme", 48_000, 120_000)], max_seconds=2.0)
    assert result == (Cue(0.0, 1.0, ("yksi kaksi",), ""),
                      Cue(1.0, 2.5, ("kolme",), ""))
    # A single word longer than the whole cue limit is still one cue.
    alone = cues([word("juttua", 0, 240_000)], max_seconds=2.0)
    assert alone == (Cue(0.0, 5.0, ("juttua",), ""),)


def test_muted_words_are_left_out():
    # The muted word's stretch is no gap between the kept words either.
    result = cues([
        word("moi", 0, 24_000),
        word("pois", 24_000, 48_000, muted=True),
        word("hei", 48_000, 72_000),
    ])
    assert result == (Cue(0.0, 1.5, ("moi hei",), ""),)
    assert cues([word("pois", 0, 24_000, muted=True)]) == ()


def test_the_speaker_is_the_person_first_then_the_raw_label():
    # A mapped person wins over the raw label; a word with neither has none.
    result = cues([
        word("moi", 0, 24_000, spk="SPEAKER_00", person="p1"),
        word("hei", 24_000, 48_000),
    ])
    assert result == (Cue(0.0, 0.5, ("moi",), "p1"),
                      Cue(0.5, 1.0, ("hei",), ""))
    # Two raw labels of one person are one speaker, so one cue.
    one = cues([
        word("moi", 0, 24_000, spk="SPEAKER_00", person="p1"),
        word("hei", 24_000, 48_000, spk="SPEAKER_01", person="p1"),
    ])
    assert one == (Cue(0.0, 1.0, ("moi hei",), "p1"),)


# -- cue times ----------------------------------------------------------------


def test_a_cue_shorter_than_half_a_second_is_stretched():
    # 0.1 s of speech would flash by; the cue holds for 0.5 s.
    result = cues([word("niinpä", 24_000, 28_800)])
    assert result == (Cue(0.5, 1.0, ("niinpä",), ""),)


def test_cues_never_overlap_even_in_crosstalk():
    # A speaks 0..0.5 s, B cuts in at 0.25 s, A again at 1.0 s. A's cue
    # loses to B's start: never overlapping beats the 0.5 s floor.
    result = cues([
        word("moi", 0, 24_000, spk="A", track="ta"),
        word("anteksi", 12_000, 36_000, spk="B", track="tb"),
        word("jatkan", 48_000, 72_000, spk="A", track="ta"),
    ])
    assert result == (Cue(0.0, 0.25, ("moi",), "A"),
                      Cue(0.25, 0.75, ("anteksi",), "B"),
                      Cue(1.0, 1.5, ("jatkan",), "A"))
    # A stretched end stops at the next cue's start, not past it.
    stretch = cues([
        word("moi", 0, 4_800, spk="A", track="ta"),
        word("sori", 14_400, 38_400, spk="B", track="tb"),
    ])
    assert stretch == (Cue(0.0, 0.3, ("moi",), "A"),
                        Cue(0.3, 0.8, ("sori",), "B"))


# -- line breaking ------------------------------------------------------------


def test_lines_break_at_word_boundaries_within_max_chars():
    result = cues([word("aurinko", 0, 24_000), word("paistaa", 24_000, 48_000),
                   word("kauniisti", 48_000, 72_000)], max_chars=16)
    assert result == (Cue(0.0, 1.5, ("aurinko paistaa", "kauniisti"), ""),)


def test_a_word_is_never_split_even_over_max_chars():
    result = cues([word("kansainvälistyminen", 0, 24_000)], max_chars=10)
    assert result == (Cue(0.0, 0.5, ("kansainvälistyminen",), ""),)


# -- file text ----------------------------------------------------------------


def test_to_srt_text_is_exact():
    result = cues([
        word("Hei", 24_000, 48_000),
        word("maal", 48_000, 60_000),
        word("anteeksi", 72_000, 108_000, spk="Pekka"),
    ], max_chars=4)
    assert to_srt(result) == (
        "1\n"
        "00:00:00,500 --> 00:00:01,250\n"
        "Hei\n"
        "maal\n"
        "\n"
        "2\n"
        "00:00:01,500 --> 00:00:02,250\n"
        "Pekka: anteeksi\n"
    )


def test_to_vtt_text_is_exact():
    result = cues([
        word("Hei", 24_000, 48_000),
        word("maal", 48_000, 60_000),
        word("anteeksi", 72_000, 108_000, spk="Pekka"),
    ], max_chars=4)
    assert to_vtt(result) == (
        "WEBVTT\n"
        "\n"
        "00:00:00.500 --> 00:00:01.250\n"
        "Hei\n"
        "maal\n"
        "\n"
        "00:00:01.500 --> 00:00:02.250\n"
        "<v Pekka>anteeksi\n"
    )


def test_finnish_letters_are_kept_through_to_the_files():
    result = cues([word("Äänite", 0, 24_000), word("öljyssä", 24_000, 48_000),
                   word("yöllä", 48_000, 72_000)])
    assert result[0].lines == ("Äänite öljyssä yöllä",)
    assert "Äänite öljyssä yöllä" in to_srt(result)
    assert "Äänite öljyssä yöllä" in to_vtt(result)


def test_an_empty_transcript_gives_no_cues_and_empty_text():
    assert cues([]) == ()
    assert to_srt(()) == ""
    assert to_vtt(()) == "WEBVTT\n"


# -- the unit contract, through the real timeline ------------------------------


def test_times_are_frames_at_the_project_rate():
    p = Project(
        rate=RATE,
        media=(Media("ma", "ma.wav", 1, 100_000),),
        tracks=(Track("ta", "ta", kind="speech",
                      clips=(Clip("ca", "ma", 0, 0, 100_000),)),),
    )
    words = timeline_words(p, {"ma": [
        {"w": "moi", "s": frames_to_flicks(24_000, RATE),
         "e": frames_to_flicks(48_000, RATE), "spk": ""},
        {"w": "hei", "s": frames_to_flicks(72_000, RATE),
         "e": frames_to_flicks(96_000, RATE), "spk": ""},
    ]})
    # The default rate is the model's own 48 000: frames become seconds.
    assert cues(words) == (Cue(0.5, 2.0, ("moi hei",), ""),)
    # Another rate converts the same frames to other seconds.
    assert cues(words, rate=24_000) == (Cue(1.0, 4.0, ("moi hei",), ""),)
