"""The automixer reports every stage per track, also the ones that are switched off
(its progress line says "Olli: debleed" even with --no-debleed). Kuulas marks those."""

from kuulas import automix


def test_a_stage_that_is_off_is_marked_skipped():
    out = automix.mark_skipped("Olli: debleed", {"speech_debleed": False})
    assert out.startswith("Olli: debleed")
    assert out != "Olli: debleed"


def test_a_stage_that_is_on_is_left_alone():
    assert automix.mark_skipped("Olli: debleed", {}) == "Olli: debleed"


def test_the_microphone_duck_is_off_by_default():
    assert automix.mark_skipped("Olli: duck", {}) != "Olli: duck"
    assert automix.mark_skipped("Olli: duck", {"speech_mic_duck": True}) == "Olli: duck"


def test_minimal_switches_the_optional_stages_off():
    assert automix.mark_skipped("Olli: debleed", {"minimal": True}) != "Olli: debleed"


def test_other_messages_are_untouched():
    for text in ("Olli: read", "Loading 5 tracks", "Summing master...", ""):
        assert automix.mark_skipped(text, {"speech_debleed": False}) == text
