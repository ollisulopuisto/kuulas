from types import SimpleNamespace

from kuulas import transcribe


def test_whisper_json_with_segments():
    data = {"segments": [{"words": [
        {"word": " Hei", "start": 0.5, "end": 0.8},
        {"word": " maailma.", "start": 0.9, "end": 1.4},
    ]}]}
    assert transcribe.parse(data, rate=1000) == [
        {"w": "Hei", "s": 500, "e": 800, "spk": ""},
        {"w": "maailma.", "s": 900, "e": 1400, "spk": ""},
    ]


def test_flat_word_list_and_speaker():
    data = [{"text": "moi", "start": 1, "end": 2, "speaker": "S1"}]
    assert transcribe.parse(data, rate=10) == [
        {"w": "moi", "s": 10, "e": 20, "spk": "S1"}]


def test_words_without_duration_get_one_frame():
    data = [{"w": "x", "s": 1.0, "e": 1.0}]
    word = transcribe.parse(data, rate=100)[0]
    assert word["e"] > word["s"]


def test_faster_whisper_words_are_normalised():
    seg = SimpleNamespace(words=[SimpleNamespace(word=" Hyvä", start=0.1, end=0.3)])
    assert transcribe.from_segments([seg], rate=1000) == [
        {"w": "Hyvä", "s": 100, "e": 300, "spk": ""}]
