"""The progress line says which step the automixer is at: "3/4 track 2/3 Kari:
debleed (2/9)". The tool does not number its steps, so Kuulas does, from the
stage words it prints (speechmix chain and stems)."""

from kuulas import automix

TRACKS = ["Olli", "Kari", "Panu"]


def tracker():
    return automix.StepTracker(TRACKS)


def test_stems_export_is_the_first_phase():
    assert tracker().stems("exporting").startswith("1/4")


def test_analysis_lines_are_the_second_phase():
    t = tracker()
    lines = ("loaded the tracks", "[automixer] block Olli 65:45.5-65:52.0: gain +3.5 dB")
    for line in lines:
        assert t.label(line).startswith("2/4"), line


def test_a_track_stage_names_the_track_and_the_stage():
    t = tracker()
    first = t.label("[automixer]   Olli: read")
    assert first.startswith("3/4")
    assert "1/3" in first
    assert "1/9" in first
    second = t.label("[automixer]   Kari: debleed")
    assert "2/3" in second
    assert "2/9" in second


def test_mastering_is_the_last_phase():
    assert tracker().label("mastering").startswith("4/4")
    assert tracker().label("[automixer] mastering pass").startswith("4/4")


def test_a_line_between_keeps_the_phase_it_is_in():
    t = tracker()
    t.label("[automixer]   Olli: read")
    assert t.label("[ääni]     vuoto Kari: nothing to remove").startswith("3/4")


def test_an_unknown_track_still_counts_without_a_total_overrun():
    t = automix.StepTracker([])
    assert "1/1" in t.label("Solo: read")


def test_a_reported_stage_is_one_that_has_finished_and_the_next_one_is_named():
    """The tool prints a stage word when the stage is DONE: the toast must not look as
    if debleed were still running while the slow plug-in stage works."""
    t = automix.StepTracker(TRACKS, {"speech_plugins": ["x.vst3"]})
    line = t.label("[automixer]   Olli: debleed")
    assert "done" in line
    assert "now plugin" in line


def test_a_stage_that_is_off_is_skipped_and_the_next_running_one_is_named():
    t = automix.StepTracker(TRACKS, {"speech_debleed": False, "speech_plugins": ["x"]})
    line = t.label("[automixer]   Olli: debleed")
    assert "skipped" in line
    assert "now plugin" in line


def test_the_plugin_stage_is_skipped_when_no_plugin_is_chosen():
    t = automix.StepTracker(TRACKS, {})
    assert "now cleanup" in t.label("[automixer]   Olli: debleed")


def test_the_last_stage_of_a_track_says_the_track_is_finished():
    t = automix.StepTracker(TRACKS, {})
    assert "finished" in t.label("[automixer]   Olli: write")
