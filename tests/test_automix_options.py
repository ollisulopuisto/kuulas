"""The automixer's command-line switches as settings (``options``): only what differs
from the tool's own default reaches the command line."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from kuulas import automix

BASE = ["automixer", "/s", "-o", "/o.wav", "--target-lufs", "-16", "--progress"]


def command(options=None, extra=None):
    settings = {"command": ["automixer"], "extra_args": extra or [],
                "options": options if options is not None else {}}
    return automix.build_command(settings, Path("/s"), Path("/o.wav"),
                                 target_lufs=-16, ad_spot=None, ad_duration=None)


def test_defaults_add_no_flags():
    assert command() == BASE
    assert command({"speech_debleed": True, "speech_mic_duck": False,
                    "music_carve_strength": 0.5, "speech_hp": True}) == BASE


def test_a_settings_dict_without_options_still_builds():
    cmd = automix.build_command({"command": ["a"], "extra_args": []}, Path("/s"),
                                Path("/o.wav"), target_lufs=-16, ad_spot=None,
                                ad_duration=None)
    assert cmd[-1] == "--progress"


@pytest.mark.parametrize(("key", "flag"), [
    ("speech_hp", "--no-speech-hp"), ("speech_peak", "--no-speech-peak"),
    ("speech_lev", "--no-speech-lev"), ("speech_desmack", "--no-speech-desmack"),
    ("speech_debleed", "--no-debleed"), ("speech_rider", "--no-rider"),
    ("block_level", "--no-block-level"), ("music_carve", "--no-music-carve"),
    ("music_duck", "--no-music-duck")])
def test_an_unchecked_default_on_stage_emits_its_no_flag(key, flag):
    assert command({key: False}) == [*BASE, flag]


def test_multiband_is_off_by_default_and_emitted_when_on():
    assert command({"speech_multiband": False}) == BASE
    assert command({"speech_multiband": True}) == [*BASE, "--speech-multiband"]


def test_mic_duck_on_with_depth():
    assert command({"speech_mic_duck": True, "mic_duck_db": -12}) == [
        *BASE, "--mic-duck", "--mic-duck-db", "-12"]
    assert command({"speech_mic_duck": True}) == [*BASE, "--mic-duck"]


def test_the_depth_alone_is_not_emitted_while_mic_ducking_is_off():
    assert command({"mic_duck_db": -12}) == BASE


def test_numbers_that_differ_are_emitted_and_those_equal_to_default_are_not():
    assert command({"speech_desmack_sensitivity": 0.8, "music_carve_strength": 0.5,
                    "music_duck_threshold": -40}) == [
        *BASE, "--speech-desmack-sensitivity", "0.8", "--music-duck-threshold", "-40"]


def test_a_number_of_a_switched_off_stage_is_not_emitted():
    assert command({"music_carve": False, "music_carve_strength": 0.9}) == [
        *BASE, "--no-music-carve"]


def test_minimal_replaces_the_switches_it_overrides():
    opts = {"minimal": True, "speech_hp": False, "speech_mic_duck": True,
            "music_carve_strength": 0.9, "speech_multiband": True}
    assert command(opts) == [*BASE, "--minimal", "--speech-multiband"]
    assert command({"minimal": True}) == [*BASE, "--minimal"]


def test_text_and_list_options():
    cmd = command({"speech_plugins": ["/p/dxRevive.vst3", "/p/b.vst3"],
                   "plugin_params": "dxrevive: mix=50", "plugin_state": "/p/s.json",
                   "track_params": "panu/dxrevive:mix=25", "music_plugins": []})
    assert cmd == [*BASE, "--speech-plugins", "/p/dxRevive.vst3", "/p/b.vst3",
                   "--plugin-params", "dxrevive: mix=50",
                   "--track-params", "panu/dxrevive:mix=25",
                   "--plugin-state", "/p/s.json"]


def test_extra_arguments_still_go_last():
    assert command({"speech_debleed": False}, ["--verbose"]) == [
        *BASE, "--no-debleed", "--verbose"]


@pytest.mark.parametrize("options", [
    {"nonsense": True}, {"speech_hp": "yes"}, {"speech_hp": 1},
    {"music_carve_strength": "x"}, {"music_carve_strength": 1.5},
    {"music_carve_strength": -0.1}, {"music_carve_strength": math.nan},
    {"music_carve_strength": math.inf}, {"music_carve_strength": True},
    {"music_duck_threshold": 5}, {"mic_duck_db": 3}, {"mic_duck_db": [1]},
    {"plugin_params": 5}, {"plugin_params": "--evil"}, {"plugin_params": "a\nb"},
    {"speech_plugins": "single"}, {"speech_plugins": ["--x"]},
    {"speech_plugins": [3]}, {"plugin_state": "x" * 100000}, "text", ["a"]])
def test_bad_options_are_refused(options):
    with pytest.raises(automix.AutomixError) as caught:
        automix.normalize_options(options)
    assert caught.value.key == "error.automix.bad_option"


def test_numbers_may_be_numeric_strings_and_empty_means_default():
    assert automix.normalize_options({"music_carve_strength": "0.7",
                                      "mic_duck_db": "", "plugin_params": ""}) == {
        "music_carve_strength": 0.7}


def test_normalising_keeps_only_what_differs_from_the_default():
    assert automix.normalize_options({"speech_hp": True, "speech_debleed": False,
                                      "music_carve_strength": 0.5}) == {
        "speech_debleed": False}


def test_options_are_stored_with_the_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("KUULAS_AUTOMIXER_FILE", str(tmp_path / "automixer.json"))
    assert automix.resolve_settings({}, home=tmp_path)["options"] == {}
    saved = automix.save_settings({"extra_args": ["--x"],
                                   "options": {"speech_debleed": False}})
    assert saved["options"] == {"speech_debleed": False}
    again = automix.resolve_settings(automix.load_settings(), home=tmp_path)
    assert again["options"] == {"speech_debleed": False}
    assert again["extra_args"] == ["--x"]
    with pytest.raises(automix.AutomixError):
        automix.save_settings({"options": {"music_carve_strength": 9}})


def test_stored_damage_does_not_break_resolving(tmp_path):
    s = automix.resolve_settings({"options": {"music_carve_strength": 9,
                                              "speech_hp": False, "zzz": 1}},
                                 home=tmp_path)
    assert s["options"] == {"speech_hp": False}


def test_specs_match_the_tool_defaults():
    specs = {s["key"]: s for s in automix.option_specs()}
    assert specs["speech_debleed"]["default"] is True
    assert specs["speech_mic_duck"]["default"] is False
    assert specs["speech_multiband"]["default"] is False
    assert specs["speech_desmack_sensitivity"]["default"] == 0.5
    assert specs["music_duck_threshold"]["default"] == -30.0
    assert specs["mic_duck_db"]["default"] is None
    assert {s["group"] for s in specs.values()} >= {"speech", "debleed", "micduck",
                                                    "music", "plugins", "minimal"}
