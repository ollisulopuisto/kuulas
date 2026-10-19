"""Tool output shown in notices has no terminal escape codes."""

from kuulas.automix import clean_output_line


def test_colour_and_erase_codes_are_removed():
    raw = "\x1b[2K\x1b[91m━━\x1b[0m\x1b[90m╸\x1b[0m \x1b[32m491.7/887.9 MB\x1b[0m"
    assert clean_output_line(raw) == "━━╸ 491.7/887.9 MB"


def test_plain_text_is_unchanged():
    assert clean_output_line("PROGRESS 70 uploading") == "PROGRESS 70 uploading"


def test_osc_title_sequences_and_bare_escapes_are_removed():
    assert clean_output_line("\x1b]0;title\x07hello\x1b") == "hello"


def test_only_the_last_carriage_return_segment_is_kept():
    assert clean_output_line("10%\r50%\r100% done") == "100% done"
