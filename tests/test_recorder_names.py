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


def test_valid_name_unicode_and_single_char():
    assert names.valid_name("A")
    assert names.valid_name("1")
    assert names.valid_name("Ä")
    assert names.valid_name("Голос")
    assert names.valid_name("マイク")
    assert names.valid_name("Φωνή")


def test_valid_name_inner_punctuation_and_underscores():
    assert names.valid_name("Host_1")
    assert names.valid_name("Track_Name-1")
    assert names.valid_name("Track (1)+2 & 3 - final")


def test_valid_name_invalid_edge_cases():
    # Empty string
    assert not names.valid_name("")

    # Leading invalid start characters
    assert not names.valid_name("_Host")
    assert not names.valid_name("-Host")
    assert not names.valid_name("+Host")
    assert not names.valid_name("'Host")

    # Disallowed characters anywhere in name
    forbidden_chars = (
        ":", "*", "?", '"', "<", ">", "|", "#", "$", "%",
        "@", "!", "^", "=", ";", "{", "}", "[", "]",
    )
    for forbidden in forbidden_chars:
        assert not names.valid_name(f"Host{forbidden}1")

    # Control characters
    assert not names.valid_name("Host\n1")
    assert not names.valid_name("Host\t1")
    assert not names.valid_name("Host\r1")
    assert not names.valid_name("Host\x001")


def test_valid_name_non_string_types():
    assert not names.valid_name(123.45)
    assert not names.valid_name(True)
    assert not names.valid_name(False)
    assert not names.valid_name(["Host"])
    assert not names.valid_name({"name": "Host"})
    assert not names.valid_name(("Host",))


def test_segment_file():
    # First segment
    assert names.segment_file("Take 1", "Host", 1) == "Take 1-Host.wav"
    assert names.segment_file("Take 2", "Guest", 1) == "Take 2-Guest.wav"

    # Later segments
    assert names.segment_file("Take 1", "Host", 2) == "Take 1-Host~2.wav"
    assert names.segment_file("Take 1", "Host", 10) == "Take 1-Host~10.wav"
    assert names.segment_file("Take 3", "Music", 42) == "Take 3-Music~42.wav"


def test_sidecar_file():
    assert names.sidecar_file("Take 1") == "Take 1.take.json"
    assert names.sidecar_file("Recording 5") == "Recording 5.take.json"


def test_journal_file():
    assert names.journal_file("Take 1") == "Take 1.journal.jsonl"
    assert names.journal_file("Session 2") == "Session 2.journal.jsonl"
