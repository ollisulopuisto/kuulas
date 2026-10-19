"""Validation and normalisation of a series template.

Pure logic, stdlib only. Errors are plain ``ValueError`` naming the field;
there is no user-facing text.
"""

import copy

import pytest

from kuulas.template_schema import validate_template


def _track(name="puhe", kind="speech", bus=None):
    track = {"name": name, "kind": kind}
    if bus is not None:
        track["bus"] = bus
    return track


def test_valid_minimal_template_defaults_buses_and_clips():
    template = {"version": 1, "name": "Sarja", "tracks": [_track()]}
    result = validate_template(template)
    assert result == {
        "version": 1,
        "name": "Sarja",
        "tracks": [{"name": "puhe", "kind": "speech", "bus": None}],
        "buses": [],
        "clips": [],
    }


def test_valid_full_template_is_normalised_copy():
    template = {
        "version": 1,
        "name": "  Sarja  ",
        "tracks": [_track("puhe", "speech", "mix"), _track("musa", "music")],
        "buses": [{"name": "mix"}],
        "clips": [
            {
                "track": "puhe",
                "media": "intro.wav",
                "length": 10.0,
                "anchor": {"from": "start", "offset": 1.5},
            }
        ],
    }
    result = validate_template(template)
    assert result["name"] == "Sarja"
    assert result["tracks"][1]["bus"] is None
    assert result["clips"][0]["anchor"] == {
        "from": "start",
        "offset": 1.5,
    }


def test_version_missing_raises():
    with pytest.raises(ValueError, match="version"):
        validate_template({"name": "Sarja", "tracks": []})


def test_version_must_be_one_raises():
    with pytest.raises(ValueError, match="version"):
        validate_template(
            {"version": 2, "name": "Sarja", "tracks": []}
        )


def test_name_empty_raises():
    with pytest.raises(ValueError, match="name"):
        validate_template({"version": 1, "name": "", "tracks": []})


def test_name_whitespace_only_raises():
    with pytest.raises(ValueError, match="name"):
        validate_template({"version": 1, "name": "   ", "tracks": []})


def test_track_names_must_be_unique():
    with pytest.raises(ValueError, match="track"):
        validate_template(
            {"version": 1, "name": "Sarja", "tracks": [_track(), _track()]}
        )


def test_track_name_empty_raises():
    with pytest.raises(ValueError, match="track name"):
        validate_template(
            {"version": 1, "name": "Sarja", "tracks": [_track("")]}
        )


def test_track_name_whitespace_only_raises():
    with pytest.raises(ValueError, match="track name"):
        validate_template(
            {"version": 1, "name": "Sarja", "tracks": [_track("   ")]}
        )


def test_kind_speech_mix_is_gone():
    with pytest.raises(ValueError, match="kind"):
        validate_template(
            {"version": 1, "name": "Sarja", "tracks": [_track(kind="speech-mix")]}
        )


def test_track_bus_must_be_listed_bus():
    with pytest.raises(ValueError, match="bus"):
        validate_template(
            {
                "version": 1,
                "name": "Sarja",
                "tracks": [_track(bus="puuttuu")],
                "buses": [{"name": "mix"}],
            }
        )


def test_bus_names_must_be_unique():
    with pytest.raises(ValueError, match="bus"):
        validate_template(
            {
                "version": 1,
                "name": "Sarja",
                "tracks": [],
                "buses": [{"name": "mix"}, {"name": "mix"}],
            }
        )


def test_clip_track_must_be_listed_track():
    with pytest.raises(ValueError, match="track"):
        validate_template(
            {
                "version": 1,
                "name": "Sarja",
                "tracks": [_track()],
                "clips": [{"track": "tuntematon", "media": "a.wav", "length": 1.0}],
            }
        )


def test_clip_media_must_be_non_empty():
    with pytest.raises(ValueError, match="media"):
        validate_template(
            {
                "version": 1,
                "name": "Sarja",
                "tracks": [_track()],
                "clips": [{"track": "puhe", "media": "", "length": 1.0}],
            }
        )


def test_clip_length_must_be_positive():
    for length in (0.0, -2.5):
        with pytest.raises(ValueError, match="length"):
            validate_template(
                {
                    "version": 1,
                    "name": "Sarja",
                    "tracks": [_track()],
                    "clips": [{"track": "puhe", "media": "a.wav", "length": length}],
                }
            )


def test_anchor_is_validated():
    with pytest.raises(ValueError, match="anchor"):
        validate_template(
            {
                "version": 1,
                "name": "Sarja",
                "tracks": [_track()],
                "clips": [
                    {
                        "track": "puhe",
                        "media": "a.wav",
                        "length": 1.0,
                        "anchor": {"from": "middle"},
                    }
                ],
            }
        )


def test_marker_anchor_is_allowed_without_checking_the_name():
    template = {
        "version": 1,
        "name": "Sarja",
        "tracks": [_track()],
        "clips": [
            {
                "track": "puhe",
                "media": "a.wav",
                "length": 1.0,
                "anchor": {"from": "marker", "name": "jingle"},
            }
        ],
    }
    result = validate_template(template)
    assert result["clips"][0]["anchor"] == {
        "from": "marker",
        "name": "jingle",
        "offset": 0.0,
    }


def test_result_is_a_deep_copy_input_not_mutated():
    template = {
        "version": 1,
        "name": "Sarja",
        "tracks": [_track()],
        "clips": [
            {
                "track": "puhe",
                "media": "a.wav",
                "length": 1.0,
                "anchor": {"from": "start"},
            }
        ],
    }
    before = copy.deepcopy(template)
    result = validate_template(template)
    assert result is not template
    assert result["tracks"] is not template["tracks"]
    assert result["clips"] is not template["clips"]
    assert result["clips"][0]["anchor"] is not template["clips"][0]["anchor"]
    assert template == before
    result["name"] = "muutettu"
    assert template["name"] == "Sarja"
