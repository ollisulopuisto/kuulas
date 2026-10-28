"""Tests for naming rules of files and takes in the recorder."""

from kuulas_recorder import names


def test_valid_name():
    # Valid names
    assert names.valid_name("Host")
    assert names.valid_name("Host 1")
    assert names.valid_name("Take 1")
    assert names.valid_name("Olli's Mic")
    assert names.valid_name("Guitar (L)")
    assert names.valid_name("Bass-DI")
    assert names.valid_name("Vocal+Reverb")
    assert names.valid_name("A, B, C")
    assert names.valid_name("Ääni")

    # Invalid characters or patterns
    assert not names.valid_name(" Host")  # Leading space
    assert not names.valid_name("Host ")  # Trailing space
    assert not names.valid_name(".Host")  # Leading dot
    assert not names.valid_name("Host.")  # Trailing dot
    assert not names.valid_name("Host~1") # Contains tilde
    assert not names.valid_name("Host/1") # Contains path separator
    assert not names.valid_name("Host\\1") # Contains path separator

    # Length limits
    assert names.valid_name("A" * 80)
    assert not names.valid_name("A" * 81)

    # Wrong types
    assert not names.valid_name(123)
    assert not names.valid_name(None)
    assert not names.valid_name(b"Host")


def test_segment_file():
    # First segment
    assert names.segment_file("Take 1", "Host", 1) == "Take 1-Host.wav"
    assert names.segment_file("Take 2", "Guest", 1) == "Take 2-Guest.wav"

    # Later segments
    assert names.segment_file("Take 1", "Host", 2) == "Take 1-Host~2.wav"
    assert names.segment_file("Take 1", "Host", 10) == "Take 1-Host~10.wav"
    assert names.segment_file("Take 3", "Music", 42) == "Take 3-Music~42.wav"

    # Names with special characters and Unicode
    assert names.segment_file("Take 1", "Ääni", 1) == "Take 1-Ääni.wav"
    assert names.segment_file("Take 1", "Ääni", 2) == "Take 1-Ääni~2.wav"
    assert names.segment_file("Session-1", "Olli's Mic", 1) == "Session-1-Olli's Mic.wav"
    assert (
        names.segment_file("Session-1", "Guitar (L)", 3)
        == "Session-1-Guitar (L)~3.wav"
    )
    assert names.segment_file("Take+1", "Vocal+Reverb", 1) == "Take+1-Vocal+Reverb.wav"

    # Large segment numbers
    assert names.segment_file("Take 1", "Host", 100) == "Take 1-Host~100.wav"


def test_sidecar_file():
    assert names.sidecar_file("Take 1") == "Take 1.take.json"
    assert names.sidecar_file("Recording 5") == "Recording 5.take.json"


def test_journal_file():
    assert names.journal_file("Take 1") == "Take 1.journal.jsonl"
    assert names.journal_file("Session 2") == "Session 2.journal.jsonl"
