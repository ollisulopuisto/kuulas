"""Tests for speech statistics over transcript words."""

from __future__ import annotations

from kuulas.speech_stats import longest_silences, shares, speaker_stats


class TestSpeakerStats:
    def test_two_speakers_known_numbers(self):
        words = [
            {
                "w": "hello",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "world",
                "s": 24_000,
                "e": 48_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "hi",
                "s": 72_000,
                "e": 96_000,
                "spk": "B",
                "person": "",
                "track": "t2",
                "muted": False,
            },
            {
                "w": "there",
                "s": 96_000,
                "e": 120_000,
                "spk": "B",
                "person": "",
                "track": "t2",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["words"] == 2
        assert stats["A"]["seconds"] == 1.0
        assert stats["A"]["turns"] == 1
        assert stats["A"]["wpm"] == 120.0
        assert stats["B"]["words"] == 2
        assert stats["B"]["seconds"] == 1.0
        assert stats["B"]["turns"] == 1
        assert stats["B"]["wpm"] == 120.0

    def test_muted_words_ignored(self):
        words = [
            {
                "w": "one",
                "s": 0,
                "e": 48_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "two",
                "s": 48_000,
                "e": 96_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": True,
            },
            {
                "w": "three",
                "s": 96_000,
                "e": 144_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["words"] == 2
        assert stats["A"]["seconds"] == 2.0
        assert stats["A"]["turns"] == 1

    def test_turn_at_speaker_change(self):
        words = [
            {
                "w": "a",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "b",
                "s": 24_000,
                "e": 48_000,
                "spk": "B",
                "person": "",
                "track": "t2",
                "muted": False,
            },
            {
                "w": "c",
                "s": 48_000,
                "e": 72_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["turns"] == 2
        assert stats["B"]["turns"] == 1

    def test_turn_at_gap_over_one_and_half_seconds(self):
        words = [
            {
                "w": "a",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "b",
                "s": 120_000,
                "e": 144_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["turns"] == 2

    def test_no_turn_at_short_gap(self):
        words = [
            {
                "w": "a",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "b",
                "s": 72_000,
                "e": 96_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["turns"] == 1

    def test_wpm_rounded_to_one_decimal(self):
        # Three words in exactly 1.5 seconds -> 120.0 wpm
        words = [
            {
                "w": "one",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "two",
                "s": 24_000,
                "e": 48_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "three",
                "s": 48_000,
                "e": 72_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["wpm"] == 120.0

    def test_wpm_zero_when_no_time(self):
        words = [
            {
                "w": "x",
                "s": 100,
                "e": 100,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert stats["A"]["wpm"] == 0

    def test_empty_input(self):
        assert speaker_stats([]) == {}

    def test_person_label_preferred_over_spk(self):
        words = [
            {
                "w": "one",
                "s": 0,
                "e": 48_000,
                "spk": "spk-0",
                "person": "alice",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert "alice" in stats
        assert "spk-0" not in stats

    def test_track_id_used_when_no_speaker(self):
        words = [
            {
                "w": "one",
                "s": 0,
                "e": 48_000,
                "spk": "",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        stats = speaker_stats(words, rate=48_000)
        assert "t1" in stats


class TestShares:
    def test_shares_sum_to_one(self):
        stats = {
            "A": {"words": 2, "seconds": 1.0, "turns": 1, "wpm": 120.0},
            "B": {"seconds": 3.0},
        }
        result = shares(stats)
        assert result["A"] == 0.25
        assert result["B"] == 0.75
        assert sum(result.values()) == 1.0

    def test_empty_shares(self):
        assert shares({}) == {}


class TestLongestSilences:
    def test_order_is_longest_first(self):
        words = [
            {
                "w": "a",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "b",
                "s": 48_000,
                "e": 72_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "c",
                "s": 200_000,
                "e": 224_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "d",
                "s": 250_000,
                "e": 274_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        silences = longest_silences(words, n=2, rate=48_000)
        assert silences == [
            (1.5, 4.166666666666667),
            (4.666666666666667, 5.208333333333333),
        ]

    def test_muted_words_ignored_for_silences(self):
        words = [
            {
                "w": "a",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "muted",
                "s": 48_000,
                "e": 72_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": True,
            },
            {
                "w": "b",
                "s": 200_000,
                "e": 224_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        silences = longest_silences(words, n=1, rate=48_000)
        assert silences == [(0.5, 4.166666666666667)]

    def test_returns_fewer_when_not_enough_gaps(self):
        words = [
            {
                "w": "a",
                "s": 0,
                "e": 24_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
            {
                "w": "b",
                "s": 48_000,
                "e": 72_000,
                "spk": "A",
                "person": "",
                "track": "t1",
                "muted": False,
            },
        ]
        silences = longest_silences(words, n=5, rate=48_000)
        assert len(silences) == 1

    def test_empty_input(self):
        assert longest_silences([]) == []
