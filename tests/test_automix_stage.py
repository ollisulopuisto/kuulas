"""Tests for automix_stage.stage_of, stage_progress_floor and stage_key (RED).

Written before the module; run them and watch them fail, then implement.
"""

from kuulas.automix_stage import stage_key, stage_of, stage_progress_floor


def test_load_stage():
    assert stage_of("PROGRESS 5 loaded the tracks") == "load"


def test_levels_stage():
    assert stage_of("PROGRESS 15 checked the levels") == "levels"


def test_speech_stage_ends_with_processed():
    assert stage_of("PROGRESS 45 kari processed") == "speech"


def test_speech_stage_step_words():
    for word in ("debleed", "cleanup", "measure", "dynamics", "lag", "duck", "write"):
        assert stage_of(f"[automixer]   olli: {word}") == "speech"


def test_master_stage():
    assert stage_of("PROGRESS 80 mastering") == "master"


def test_master_stage_finnish():
    assert stage_of("[ääni] masterointi kierros 2: ...") == "master"


def test_write_stage():
    assert stage_of("PROGRESS 92 writing the mix") == "write"


def test_done_stage():
    assert stage_of("PROGRESS 100 done") == "done"
    assert stage_of("done") == "done"


def test_case_insensitive():
    assert stage_of("MASTERING") == "master"
    assert stage_of("Done") == "done"
    assert stage_of("Writing the Mix") == "write"
    assert stage_of("LOADED THE TRACKS") == "load"


def test_unknown_message_returns_none():
    assert stage_of("something unrelated") is None
    assert stage_of("") is None
    assert stage_of("   ") is None


def test_write_beats_speech_step_word():
    # "writing the mix" contains the step word "write" but is the write stage.
    assert stage_of("writing the mix") == "write"


def test_progress_floor_per_stage():
    assert stage_progress_floor("load") == 0.0
    assert stage_progress_floor("levels") == 0.05
    assert stage_progress_floor("speech") == 0.15
    assert stage_progress_floor("master") == 0.8
    assert stage_progress_floor("write") == 0.92
    assert stage_progress_floor("done") == 1.0


def test_progress_floor_unknown_raises():
    try:
        stage_progress_floor("weird")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for an unknown stage")


def test_stage_key():
    assert stage_key("master") == "ui.automix.stage.master"
    assert stage_key("done") == "ui.automix.stage.done"
    assert stage_key(None) is None
    assert stage_key("weird") is None
