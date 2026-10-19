"""Building a series template from what a project holds (WP66), logic only.

``build_template`` turns the project's tracks and buses and the standing
clips the user picked — positions in frames at ``rate`` — into the plain
dict ``validate_template`` (in ``kuulas.template_schema``) accepts: tracks
and buses in their order, and each picked clip as a reference to its
recording with a length in float seconds and an anchor, from the programme
start, or from the end when the clip's end sits within a second of the
programme end. The module itself is stdlib-only and imports nothing from
kuulas; this test imports ``validate_template`` once, as the task allows,
to pin that the built template passes it.
"""

import copy

import pytest

from kuulas.template_build import build_template
from kuulas.template_schema import validate_template

RATE = 48_000
SECOND = RATE


def _speech(name="Olli", bus=None):
    return {"name": name, "kind": "speech", "bus": bus}


def _music(name="Musa", bus=None):
    return {"name": name, "kind": "music", "bus": bus}


# -- the whole template -------------------------------------------------------


def test_builds_the_template_shape_with_every_order_kept():
    tracks = [
        _speech("Olli", "puhe"),
        _music("Musa"),
        _speech("Vieras", "puhe"),
    ]
    buses = ["puhe", "musiikki"]
    chosen = [
        {"track": "Musa", "media": "jingle.wav", "start": 43_200, "length": 96_000},
        {"track": "Olli", "media": "intro.wav", "start": 0, "length": 24_000},
    ]
    template = build_template("Sarja", tracks, buses, chosen, 3_600_000, RATE)
    assert template == {
        "version": 1,
        "name": "Sarja",
        "tracks": [
            {"name": "Olli", "kind": "speech", "bus": "puhe"},
            {"name": "Musa", "kind": "music", "bus": None},
            {"name": "Vieras", "kind": "speech", "bus": "puhe"},
        ],
        "buses": [{"name": "puhe"}, {"name": "musiikki"}],
        "clips": [
            {
                "track": "Musa",
                "media": "jingle.wav",
                "length": 2.0,
                "anchor": {"from": "start", "offset": 0.9},
            },
            {
                "track": "Olli",
                "media": "intro.wav",
                "length": 0.5,
                "anchor": {"from": "start", "offset": 0.0},
            },
        ],
    }


def test_the_output_passes_validate_template():
    tracks = [_speech("Olli", "puhe"), _music("Musa", "mb")]
    chosen = [
        {"track": "Olli", "media": "intro.wav", "start": 0, "length": 24_000},
        {"track": "Musa", "media": "outro.wav", "start": 3_513_600, "length": 43_200},
    ]
    template = build_template("Sarja", tracks, ["puhe", "mb"], chosen,
                              3_600_000, RATE)
    normalised = validate_template(template)
    assert normalised["name"] == "Sarja"
    assert normalised["tracks"] == template["tracks"]
    assert normalised["clips"] == template["clips"]


def test_nothing_chosen_builds_an_empty_template():
    template = build_template("Sarja", [], [], [], SECOND * 2, RATE)
    assert template == {
        "version": 1,
        "name": "Sarja",
        "tracks": [],
        "buses": [],
        "clips": [],
    }


# -- anchors ------------------------------------------------------------------


def test_a_clip_ending_half_a_second_before_the_end_anchors_from_the_end():
    chosen = [{"track": "Musa", "media": "outro.wav",
               "start": 3_532_800, "length": 43_200}]
    template = build_template("Sarja", [_music()], ["mb"], chosen,
                              3_600_000, RATE)
    assert template["clips"][0]["anchor"] == {"from": "end", "offset": 0.5}


def test_a_gap_of_exactly_one_second_still_anchors_from_the_end():
    chosen = [{"track": "Musa", "media": "outro.wav",
               "start": 46_800, "length": 1_200}]
    template = build_template("Sarja", [_music()], ["mb"], chosen,
                              SECOND * 2, RATE)
    assert template["clips"][0]["anchor"] == {"from": "end", "offset": 1.0}


def test_one_frame_outside_the_window_anchors_from_the_start():
    chosen = [{"track": "Musa", "media": "aita.wav",
               "start": 46_800, "length": 1_199}]
    template = build_template("Sarja", [_music()], ["mb"], chosen,
                              SECOND * 2, RATE)
    assert template["clips"][0]["anchor"] == {"from": "start", "offset": 0.975}


def test_a_clip_running_past_the_end_clamps_its_offset_at_zero():
    chosen = [
        {"track": "Musa", "media": "pitka.wav", "start": 47_000, "length": 2_400},
        {"track": "Musa", "media": "myoha.wav", "start": 50_000, "length": 48_000},
    ]
    template = build_template("Sarja", [_music()], ["mb"], chosen, SECOND, RATE)
    assert template["clips"][0]["anchor"] == {"from": "end", "offset": 0.0}
    assert template["clips"][1]["anchor"] == {"from": "end", "offset": 0.0}


def test_an_early_clip_anchors_from_the_start_at_another_rate():
    chosen = [{"track": "Olli", "media": "intro.wav",
               "start": 44_100, "length": 22_050}]
    template = build_template("Sarja", [_speech()], [], chosen,
                              4_410_000, 44_100)
    assert template["clips"][0]["length"] == 0.5
    assert template["clips"][0]["anchor"] == {"from": "start", "offset": 1.0}


def test_lengths_and_offsets_are_float_seconds():
    chosen = [{"track": "Olli", "media": "pikkubitti.wav",
               "start": 1, "length": 1}]
    template = build_template("Sarja", [_speech()], [], chosen,
                              SECOND * 2, RATE)
    clip = template["clips"][0]
    assert clip["length"] == 1 / 48_000
    assert isinstance(clip["length"], float)
    assert clip["anchor"] == {"from": "start", "offset": 1 / 48_000}
    assert isinstance(clip["anchor"]["offset"], float)


# -- errors -------------------------------------------------------------------


def test_a_clip_on_an_unknown_track_raises_naming_the_track():
    chosen = [{"track": "Haamu", "media": "a.wav",
               "start": 0, "length": SECOND}]
    with pytest.raises(ValueError, match="Haamu"):
        build_template("Sarja", [_speech()], [], chosen, SECOND * 2, RATE)


def test_the_unknown_track_is_named_from_the_first_bad_clip_in_order():
    chosen = [
        {"track": "Olli", "media": "a.wav", "start": 0, "length": SECOND},
        {"track": "Haamu", "media": "b.wav", "start": 0, "length": SECOND},
    ]
    with pytest.raises(ValueError, match="Haamu"):
        build_template("Sarja", [_speech()], [], chosen, SECOND * 2, RATE)


def test_a_rate_of_zero_or_less_raises():
    for rate in (0, -48_000):
        with pytest.raises(ValueError, match="rate"):
            build_template("Sarja", [_speech()], [], [], SECOND * 2, rate)


def test_a_negative_programme_length_raises():
    with pytest.raises(ValueError, match="programme"):
        build_template("Sarja", [_speech()], [], [], -1, RATE)


def test_a_name_empty_after_strip_raises():
    for name in ("", "   ", "\t \n"):
        with pytest.raises(ValueError, match="name"):
            build_template(name, [_speech()], [], [], SECOND * 2, RATE)


def test_a_non_string_name_raises_the_same_value_error():
    with pytest.raises(ValueError, match="name"):
        build_template(None, [_speech()], [], [], SECOND * 2, RATE)


# -- the inputs and the small print --------------------------------------------


def test_extra_track_keys_are_dropped():
    tracks = [{"name": "Olli", "kind": "speech", "bus": "puhe", "colour": "#fff"}]
    template = build_template("Sarja", tracks, ["puhe"], [], SECOND * 2, RATE)
    assert template["tracks"] == [
        {"name": "Olli", "kind": "speech", "bus": "puhe"}
    ]


def test_a_track_without_a_bus_key_means_bus_none():
    tracks = [{"name": "Musa", "kind": "music"}]
    template = build_template("Sarja", tracks, [], [], SECOND * 2, RATE)
    assert template["tracks"] == [{"name": "Musa", "kind": "music", "bus": None}]


def test_the_name_is_stored_stripped():
    template = build_template("  Sarja  ", [], [], [], SECOND * 2, RATE)
    assert template["name"] == "Sarja"


def test_no_input_list_or_dict_is_touched():
    tracks = [_speech("Olli", "puhe")]
    buses = ["puhe"]
    chosen = [{"track": "Olli", "media": "intro.wav",
               "start": 43_200, "length": 24_000}]
    tracks_before = copy.deepcopy(tracks)
    buses_before = list(buses)
    chosen_before = copy.deepcopy(chosen)
    template = build_template("Sarja", tracks, buses, chosen,
                              SECOND * 2, RATE)
    assert tracks == tracks_before
    assert buses == buses_before
    assert chosen == chosen_before
    assert template["tracks"][0] is not tracks[0]
    assert template["buses"][0] is not buses[0]
    assert template["clips"][0] is not chosen[0]
    assert template["clips"][0]["anchor"] is not chosen[0]
