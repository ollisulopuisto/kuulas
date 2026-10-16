from types import SimpleNamespace

from kuulas import transcribe
from kuulas.clock import FLICKS

# Words are on the recording clock, in flicks from the media's start
# (docs/FORMAT.md); WP30 changed the unit from frames, not the values' meaning.
MS = FLICKS // 1000


def test_whisper_json_with_segments():
    data = {"segments": [{"words": [
        {"word": " Hei", "start": 0.5, "end": 0.8},
        {"word": " maailma.", "start": 0.9, "end": 1.4},
    ]}]}
    assert transcribe.parse(data) == [
        {"w": "Hei", "s": 500 * MS, "e": 800 * MS, "spk": ""},
        {"w": "maailma.", "s": 900 * MS, "e": 1400 * MS, "spk": ""},
    ]


def test_flat_word_list_and_speaker():
    data = [{"text": "moi", "start": 1, "end": 2, "speaker": "S1"}]
    assert transcribe.parse(data) == [
        {"w": "moi", "s": FLICKS, "e": 2 * FLICKS, "spk": "S1"}]


def test_words_without_duration_get_one_frame():
    data = [{"w": "x", "s": 1.0, "e": 1.0}]
    word = transcribe.parse(data)[0]
    assert word["e"] > word["s"]


def test_faster_whisper_words_are_normalised():
    seg = SimpleNamespace(words=[SimpleNamespace(word=" Hyvä", start=0.1, end=0.3)])
    assert transcribe.from_segments([seg]) == [
        {"w": "Hyvä", "s": 100 * MS, "e": 300 * MS, "spk": ""}]
