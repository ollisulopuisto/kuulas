"""The bounded speaker balance option for compatible automixers."""

from pathlib import Path

from kuulas import automix
from kuulas.hand_adjusted import balance_cap

BASE = ["automixer", "/s", "-o", "/o.wav", "--target-lufs", "-16", "--progress"]
YES = {"balance_speakers_max_db": True}
NO = {"balance_speakers_max_db": False}


def runner(help_text):
    def run_process(cmd, cwd, on_line, cancel):
        for line in help_text.splitlines():
            on_line(line)
        return 0
    return run_process


def command(options, supported=None):
    settings = {"command": ["automixer"], "extra_args": [], "options": options}
    return automix.build_command(settings, Path("/s"), Path("/o.wav"), target_lufs=-16,
                                 ad_spot=None, ad_duration=None, supported=supported)


def test_spec_is_bounded_speech_number_with_automixer_default():
    spec = automix.OPTIONS["balance_speakers_max_db"]
    assert (spec["flag"], spec["kind"], spec["default"], spec["group"]) == (
        "--balance-speakers-max-db", "number", 6.0, "speech")
    assert (spec["min"], spec["max"]) == (0.0, 6.0)
    assert "balance_speakers_max_db" in automix.GATED


def test_default_cap_is_not_stored_or_sent():
    assert automix.normalize_options({"balance_speakers_max_db": 6}) == {}
    assert command({"balance_speakers_max_db": 6}, supported=YES) == BASE


def test_cap_is_range_checked_and_only_differences_are_stored():
    assert automix.normalize_options({"balance_speakers_max_db": 2.5}) == {
        "balance_speakers_max_db": 2.5}
    assert automix.normalize_options({"balance_speakers_max_db": 0}) == {
        "balance_speakers_max_db": 0.0}
    for bad in (-0.1, 6.1, float("nan"), "x", True):
        try:
            automix.normalize_options({"balance_speakers_max_db": bad})
        except automix.AutomixError:
            continue
        raise AssertionError(f"accepted invalid cap {bad!r}")


def test_project_rule_uses_the_existing_balance_cap():
    assert balance_cap([]) == 6.0
    assert balance_cap([{"kind": "speech", "gain_db": 0.2}]) == 2.5
    assert balance_cap([], keep=True) == 0.0


def test_changed_cap_is_sent_when_supported_and_dropped_when_not():
    assert command({"balance_speakers_max_db": 2.5}, supported=YES) == [
        *BASE, "--balance-speakers-max-db", "2.5"]
    assert command({"balance_speakers_max_db": 2.5}, supported=NO) == BASE


def test_probe_detects_the_flag_in_help():
    automix.clear_capability_cache()
    newer = runner("usage: automixer\n  --balance-speakers-max-db FLOAT\n")
    older = runner("usage: automixer\n  --minimal\n")
    assert automix.capabilities(["automixer"], None, run_process=newer) == {
        **YES, "bed_under_speech_db": False}
    automix.clear_capability_cache()
    assert automix.capabilities(["automixer"], None, run_process=older) == {
        **NO, "bed_under_speech_db": False}


def test_unsupported_cap_is_dropped_with_a_specific_warning():
    kept, warnings = automix.gate_options(
        {"balance_speakers_max_db": 2.5}, ["automixer"], None,
        run_process=runner("usage: automixer\n"))
    assert kept == {}
    assert len(warnings) == 1
    assert "bounded speaker balance" in warnings[0]


def test_log_line_includes_cap_and_reason():
    assert automix.balance_cap_line(6.0) == "Speaker balance maximum: 6 dB (Automatic)"
    assert automix.balance_cap_line(2.5) == (
        "Speaker balance maximum: 2.5 dB (You adjusted levels by hand)")
    assert automix.balance_cap_line(0.0) == (
        "Speaker balance maximum: 0 dB (Keep my levels)")


def test_the_cap_is_per_project_and_never_stored_in_the_settings(tmp_path, monkeypatch):
    """A cap chosen for one project must not become the default of the next one."""
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    stored = automix.save_settings({"options": {"balance_speakers_max_db": 2.5,
                                                "speech_multiband": True}})
    assert "balance_speakers_max_db" not in stored.get("options", {})
    assert stored["options"]["speech_multiband"] is True


def test_a_run_without_an_explicit_cap_takes_the_projects_own():
    adjusted = [{"kind": "speech", "gain_db": -6.0, "clips": []}]
    untouched = [{"kind": "speech", "gain_db": 0.0, "clips": []}]
    assert automix.with_project_balance({}, adjusted) == {"balance_speakers_max_db": 2.5}
    assert automix.with_project_balance({}, untouched) == {}  # the tool default
    # an explicit choice (the dialog's) is never replaced
    assert automix.with_project_balance(
        {"balance_speakers_max_db": 0.0}, adjusted) == {"balance_speakers_max_db": 0.0}
