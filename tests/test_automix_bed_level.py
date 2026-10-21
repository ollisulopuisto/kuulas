"""The music-bed level option (--bed-under-speech-db) and the check that the installed
automixer knows it (a capability probe: ``--help`` is parsed, never fatal, cached)."""

from __future__ import annotations

import math
import os
import threading
from pathlib import Path

import pytest

from kuulas import automix

BASE = ["automixer", "/s", "-o", "/o.wav", "--target-lufs", "-16", "--progress"]
HELP_NEW = "usage: automixer\n  --bed-under-speech-db FLOAT  music level\n  --minimal\n"
HELP_OLD = "usage: automixer\n  --minimal\n"
YES = {"bed_under_speech_db": True, "balance_speakers_max_db": False}
NO = {"bed_under_speech_db": False, "balance_speakers_max_db": False}


def fake_help(text, calls=None, code=0):
    def run_process(cmd, cwd, on_line, cancel):
        if calls is not None:
            calls.append(cmd)
        for line in text.splitlines():
            on_line(line)
        return code
    return run_process


def raising(error):
    def run_process(cmd, cwd, on_line, cancel):
        raise error
    return run_process


@pytest.fixture(autouse=True)
def _fresh_cache():
    automix.clear_capability_cache()


def command(options, supported=None):
    settings = {"command": ["automixer"], "extra_args": [], "options": options}
    return automix.build_command(settings, Path("/s"), Path("/o.wav"), target_lufs=-16,
                                 ad_spot=None, ad_duration=None, supported=supported)


def test_spec_is_a_music_number_with_the_tool_default():
    spec = automix.OPTIONS["bed_under_speech_db"]
    assert (spec["flag"], spec["kind"], spec["default"], spec["group"]) == (
        "--bed-under-speech-db", "number", 1.0, "music")
    assert (spec["min"], spec["max"]) == (-30.0, 6.0)


@pytest.mark.parametrize(
    "bad", [-30.5, 6.5, math.nan, math.inf, -math.inf, "x", True, [1]])
def test_bed_level_out_of_range_or_not_finite_is_refused(bad):
    with pytest.raises(automix.AutomixError):
        automix.normalize_options({"bed_under_speech_db": bad})


@pytest.mark.parametrize("ok", [-30, 6, -10.5, "-8", "-8,5"])
def test_bed_level_in_range_is_kept(ok):
    assert "bed_under_speech_db" in automix.normalize_options({"bed_under_speech_db": ok})


def test_the_default_is_not_stored_or_sent():
    assert automix.normalize_options({"bed_under_speech_db": 1}) == {}
    assert command({"bed_under_speech_db": 1}, supported=YES) == BASE


def test_a_changed_level_is_sent_when_supported():
    assert command({"bed_under_speech_db": -10}, supported=YES) == [
        *BASE, "--bed-under-speech-db", "-10"]


def test_a_changed_level_is_not_sent_when_unsupported():
    assert command({"bed_under_speech_db": -10}, supported=NO) == BASE


def test_probe_parses_the_help():
    new = fake_help(HELP_NEW)
    assert automix.capabilities(["automixer"], None, run_process=new) == YES
    automix.clear_capability_cache()
    old = fake_help(HELP_OLD)
    assert automix.capabilities(["automixer"], None, run_process=old) == NO


def test_probe_runs_help_once_and_is_cached(tmp_path):
    calls: list = []
    for _ in range(3):
        automix.capabilities(["automixer"], str(tmp_path),
                             run_process=fake_help(HELP_NEW, calls))
    assert calls == [["automixer", "--help"]]


def test_probe_cache_follows_the_program_mtime(tmp_path):
    exe = tmp_path / "automixer"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    calls: list = []
    automix.capabilities([str(exe)], None, run_process=fake_help(HELP_OLD, calls))
    os.utime(exe, (1_000_000, 1_000_000))
    caps = automix.capabilities([str(exe)], None, run_process=fake_help(HELP_NEW, calls))
    assert len(calls) == 2
    assert caps == YES


@pytest.mark.parametrize("runner", [
    raising(FileNotFoundError("nope")), raising(OSError("boom")),
    raising(RuntimeError("odd")), fake_help(HELP_NEW, code=2)])
def test_probe_failure_means_unsupported_and_never_raises(runner):
    assert automix.capabilities(["automixer"], None, run_process=runner) == NO


def test_probe_times_out_through_the_cancel_event():
    seen = {}

    def hang(cmd, cwd, on_line, cancel):
        seen["cancel"] = cancel
        assert cancel.wait(5)  # the probe's own timer sets it
        return -15

    assert automix.capabilities(["automixer"], None, run_process=hang, timeout=0.05) == NO
    assert isinstance(seen["cancel"], threading.Event)


def test_gate_drops_an_unsupported_option_and_warns():
    options = {"bed_under_speech_db": -10, "speech_debleed": False}
    kept, warnings = automix.gate_options(
        options, ["automixer"], None, run_process=fake_help(HELP_OLD))
    assert kept == {"speech_debleed": False}
    assert len(warnings) == 1
    assert "does not support" in warnings[0]


def test_gate_keeps_a_supported_option_silently():
    options = {"bed_under_speech_db": -10}
    kept, warnings = automix.gate_options(
        options, ["automixer"], None, run_process=fake_help(HELP_NEW))
    assert kept == options
    assert warnings == []


def test_gate_does_not_probe_when_the_option_is_not_set():
    calls: list = []
    kept, warnings = automix.gate_options(
        {"speech_debleed": False}, ["automixer"], None, run_process=fake_help("", calls))
    assert (kept, warnings, calls) == ({"speech_debleed": False}, [], [])
