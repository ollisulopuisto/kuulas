"""The transcript as plain text and Markdown: paragraphs per speaker.

The word dicts are exactly what ``transcript.timeline_words`` returns:
``s``/``e`` in frames at the project rate (48 000 here), ``spk``/``person``
for the speaker, ``muted`` for words no clip plays audibly.
"""

from kuulas.clock import frames_to_flicks
from kuulas.model import Clip, Media, Project, Track
from kuulas.transcript import timeline_words
from kuulas.transcript_text import Paragraph, paragraphs, to_markdown, to_text

RATE = 48_000


def word(text: str, s: int, e: int, *, track: str = "ta", spk: str = "",
         person: str = "", muted: bool = False) -> dict:
    """A word dict exactly as ``timeline_words`` gives it (frames at RATE)."""
    return {"w": text, "spk": spk, "person": person, "s": s, "e": e,
            "track": track, "clip": "ca", "media": "ma", "index": 0,
            "muted": muted}


# -- grouping ----------------------------------------------------------------


def test_a_speaker_change_starts_a_new_paragraph():
    result = paragraphs([
        word("moi", 0, 24_000, spk="A"),
        word("hei", 24_000, 48_000, spk="A"),
        word("taas", 48_000, 72_000, spk="B"),
    ])
    assert result == (
        Paragraph(0.0, 1.0, "moi hei", "A"),
        Paragraph(1.0, 1.5, "taas", "B"),
    )


def test_a_track_change_starts_a_new_paragraph():
    # Same speaker, no gap break (0.5 s <= 1.5 s): only the track splits.
    result = paragraphs([
        word("moi", 0, 24_000, spk="A", track="ta"),
        word("hei", 48_000, 72_000, spk="A", track="tb"),
    ])
    assert result == (
        Paragraph(0.0, 0.5, "moi", "A"),
        Paragraph(1.0, 1.5, "hei", "A"),
    )


def test_a_gap_over_gap_seconds_starts_a_new_paragraph():
    # Exactly gap_seconds (1.5 s = 72 000 frames) is not over it: one
    # paragraph spanning the pause.
    tight = paragraphs([word("moi", 0, 24_000), word("hei", 96_000, 120_000)])
    assert tight == (Paragraph(0.0, 2.5, "moi hei", ""),)
    # One frame more splits it.
    split = paragraphs([word("moi", 0, 24_000), word("hei", 96_001, 168_000)])
    assert split == (Paragraph(0.0, 0.5, "moi", ""),
                     Paragraph(96_001 / RATE, 3.5, "hei", ""))


def test_muted_words_are_left_out():
    # The muted word's stretch is no gap between the kept words either.
    result = paragraphs([
        word("moi", 0, 24_000),
        word("pois", 24_000, 48_000, muted=True),
        word("hei", 48_000, 72_000),
    ])
    assert result == (Paragraph(0.0, 1.5, "moi hei", ""),)
    assert paragraphs([word("pois", 0, 24_000, muted=True)]) == ()


def test_the_speaker_is_the_person_first_then_the_raw_label():
    # A mapped person wins over the raw label; a word with neither has none.
    result = paragraphs([
        word("moi", 0, 24_000, spk="SPEAKER_00", person="p1"),
        word("hei", 24_000, 48_000),
    ])
    assert result == (Paragraph(0.0, 0.5, "moi", "p1"),
                      Paragraph(0.5, 1.0, "hei", ""))
    # Two raw labels of one person are one speaker, so one paragraph.
    one = paragraphs([
        word("moi", 0, 24_000, spk="SPEAKER_00", person="p1"),
        word("hei", 24_000, 48_000, spk="SPEAKER_01", person="p1"),
    ])
    assert one == (Paragraph(0.0, 1.0, "moi hei", "p1"),)


def test_a_paragraph_ends_with_the_latest_word_end():
    # A long early word can outlast a later short one: the end is the
    # latest end, not the last word's.
    result = paragraphs([word("pitka", 0, 120_000), word("sana", 24_000, 48_000)])
    assert result == (Paragraph(0.0, 2.5, "pitka sana", ""),)


# -- rendering ----------------------------------------------------------------


def test_to_text_renders_speaker_timestamp_text_and_blank_lines():
    result = paragraphs([
        word("moi", 0, 24_000, spk="Pekka"),
        word("ihan", 24_000, 48_000, spk="Pekka"),
        word("anteeksi", 144_000, 168_000, spk="Maija"),
    ])
    assert to_text(result) == (
        "Pekka [0:00:00]\n"
        "moi ihan\n"
        "\n"
        "Maija [0:00:03]\n"
        "anteeksi\n"
    )


def test_to_text_without_timestamps():
    result = paragraphs([
        word("moi", 0, 24_000, spk="Pekka"),
        word("hei", 144_000, 168_000, spk="Maija"),
    ])
    assert to_text(result, timestamps=False) == (
        "Pekka\n"
        "moi\n"
        "\n"
        "Maija\n"
        "hei\n"
    )


def test_to_text_without_a_speaker():
    # No speaker: the timestamp stands alone on the header line; without
    # a speaker and timestamps there is no header line, only the text.
    result = paragraphs([word("moi", 96_000, 120_000)])
    assert to_text(result) == "[0:00:02]\nmoi\n"
    assert to_text(result, timestamps=False) == "moi\n"


def test_to_markdown_renders_bold_speaker_and_time():
    result = paragraphs([
        word("moi", 0, 24_000, spk="Pekka"),
        word("hei", 144_000, 168_000, spk="Maija"),
    ])
    assert to_markdown(result) == (
        "**Pekka** (0:00:00)\n"
        "moi\n"
        "\n"
        "**Maija** (0:00:03)\n"
        "hei\n"
    )


def test_to_markdown_without_a_speaker():
    # No speaker to bold: the time stands in the parentheses alone.
    result = paragraphs([word("moi", 96_000, 120_000)])
    assert to_markdown(result) == "(0:00:02)\nmoi\n"


# -- the timestamp ------------------------------------------------------------


def test_the_timestamp_counts_hours_over_an_hour():
    # 3662 s prints 1:01:02: the hours are plain, minutes and seconds
    # two wide.
    words = [word("moi", 3662 * RATE, 3663 * RATE, spk="Pekka")]
    assert to_text(paragraphs(words)) == "Pekka [1:01:02]\nmoi\n"
    # Seconds round and carry into the minutes: 59.7 s is 0:01:00.
    late = [word("moi", round(59.7 * RATE), 60 * RATE)]
    assert to_text(paragraphs(late)) == "[0:01:00]\nmoi\n"


# -- file text ----------------------------------------------------------------


def test_finnish_letters_are_kept_through_to_the_files():
    result = paragraphs([word("Äänite", 0, 24_000), word("öljyssä", 24_000, 48_000),
                         word("yöllä", 48_000, 72_000)])
    assert result[0].text == "Äänite öljyssä yöllä"
    assert "Äänite öljyssä yöllä" in to_text(result)
    assert "Äänite öljyssä yöllä" in to_markdown(result)


def test_an_empty_transcript_gives_no_paragraphs_and_empty_text():
    assert paragraphs([]) == ()
    assert to_text(()) == ""
    assert to_markdown(()) == ""


def test_no_trailing_whitespace():
    result = paragraphs([
        word("moi", 0, 24_000, spk="Pekka"),
        word("hei", 144_000, 168_000, spk="Maija"),
    ])
    for text in (to_text(result), to_text(result, timestamps=False),
                 to_markdown(result)):
        # No line ends in spaces, and the file ends with exactly one
        # newline.
        for line in text.splitlines():
            assert line == line.rstrip()
        assert text.endswith("\n")
        assert not text.endswith("\n\n")


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
    assert paragraphs(words) == (Paragraph(0.5, 2.0, "moi hei", ""),)
    # Another rate converts the same frames to other seconds.
    assert paragraphs(words, rate=24_000) == (Paragraph(1.0, 4.0, "moi hei", ""),)
