"""Series settings (owner, 2026-10-21): the pure part. What a series carries
(track layout, Auto-Silence options, the automixer's de-bleed values), how the
project's values are read, compared and applied. docs/design/SERIES.md."""

from __future__ import annotations

from dataclasses import replace

from kuulas import ops, series_settings
from kuulas.model import Clip, Project
from kuulas.silence_options import SilenceOptions


def _show() -> Project:
    p = Project()
    p = ops.add_bus(p, "b1", "Voices")
    p = ops.set_bus(p, "b1", kind="speech", gain_db=-1.0)
    p = ops.add_track(p, "t1", "Olli", bus="b1")
    p = ops.set_track(p, "t1", gain_db=-2.5, pan=-0.3, mono=True, speaker="Olli")
    p = ops.add_track(p, "t2", "Ville", bus="b1")
    p = ops.add_track(p, "t3", "Music", kind="music")
    return ops.set_track(p, "t3", target_lufs=-24.0, duck=True)


def test_layout_names_buses_by_name_and_keeps_the_track_order():
    layout = series_settings.layout_of(_show())
    assert [t["name"] for t in layout["tracks"]] == ["Olli", "Ville", "Music"]
    olli = layout["tracks"][0]
    assert olli == {"name": "Olli", "kind": "speech", "speaker": "Olli", "bus": "Voices",
                    "gain_db": -2.5, "pan": -0.3, "mono": True, "target_lufs": None,
                    "duck": None, "follow_bus_role": True}
    assert layout["tracks"][2]["bus"] is None
    assert layout["tracks"][2]["target_lufs"] == -24.0
    assert layout["buses"] == [{"name": "Voices", "kind": "speech", "gain_db": -1.0,
                                "pan": 0.0, "mute": False}]


def test_a_new_episode_gets_the_same_layout():
    layout = series_settings.layout_of(_show())
    fresh = series_settings.apply_layout(Project(), layout)
    assert series_settings.layout_of(fresh) == layout
    assert [t.clips for t in fresh.tracks] == [(), (), ()]


def test_applying_twice_adds_nothing_twice():
    layout = series_settings.layout_of(_show())
    once = series_settings.apply_layout(Project(), layout)
    twice = series_settings.apply_layout(once, layout)
    assert [t.id for t in twice.tracks] == [t.id for t in once.tracks]
    assert [b.id for b in twice.buses] == [b.id for b in once.buses]


def test_apply_updates_same_named_tracks_and_never_removes_or_empties_one():
    layout = series_settings.layout_of(_show())
    p = ops.add_track(Project(), "x", "olli ")  # same name, other case and space
    p = ops.add_track(p, "keep", "Guest")
    clip = Clip(id="c1", media="m1", start=0, offset=0, length=480)
    p = replace(p, tracks=(replace(p.tracks[0], clips=(clip,)), p.tracks[1]))
    out = series_settings.apply_layout(p, layout)
    names = [t.name for t in out.tracks]
    assert names == ["olli ", "Guest", "Ville", "Music"]  # kept, kept, added, added
    olli = out.track("x")
    assert olli.clips == (clip,)
    assert olli.gain_db == -2.5
    assert olli.mono is True
    assert out.bus(olli.bus).name == "Voices"
    assert out.track("keep").gain_db == 0.0


def test_a_layout_with_damage_is_tamed_not_fatal():
    layout = {"tracks": [{"name": "A", "kind": "noise", "gain_db": "x"},
                         {"name": ""}, "junk", {"name": "B", "bus": "Nowhere"}],
              "buses": [{"name": "Voices", "kind": "speech"}, {"nope": 1}]}
    clean = series_settings.normalise_layout(layout)
    assert [t["name"] for t in clean["tracks"]] == ["A", "B"]
    assert clean["tracks"][0]["kind"] == "speech"
    assert clean["tracks"][0]["gain_db"] == 0.0
    assert clean["tracks"][1]["bus"] is None
    p = series_settings.apply_layout(Project(), layout)
    assert [t.name for t in p.tracks] == ["A", "B"]


def test_automix_values_fill_the_tool_defaults_for_the_series_keys_only():
    values = series_settings.automix_values({"speech_debleed": False, "minimal": True,
                                             "mic_duck_db": -12.0})
    assert set(values) == set(series_settings.AUTOMIX_KEYS)
    assert values["speech_debleed"] is False
    assert values["speech_rider"] is True
    assert values["mic_duck_db"] == -12.0
    assert "minimal" not in values


def test_settings_are_normalised_tolerantly():
    clean = series_settings.normalise_settings({
        "auto_silence": {"margin_db": 99, "method": "nonsense"},
        "automix": {"speech_debleed": "yes", "speech_rider": False, "minimal": True},
        "layout": {"tracks": [{"name": "A"}]},
        "unknown": 1})
    assert clean["auto_silence"]["margin_db"] == 20.0  # clamped
    assert clean["auto_silence"]["method"] == "threshold"  # bad: the default
    defaults = series_settings.automix_values({})
    assert clean["automix"] == {**defaults, "speech_rider": False}
    assert clean["layout"]["tracks"][0]["name"] == "A"
    assert "unknown" not in clean
    assert series_settings.normalise_settings("junk") == {}


def test_differences_name_the_sections_that_differ():
    layout = series_settings.layout_of(_show())
    silence = SilenceOptions().as_dict()
    automix = series_settings.automix_values({})
    series = {"layout": layout, "auto_silence": silence, "automix": automix}
    same = {"layout": layout, "auto_silence": dict(silence), "automix": dict(automix)}
    assert series_settings.differences(same, series) == []
    louder = {**same, "auto_silence": {**silence, "margin_db": 9.0}}
    assert series_settings.differences(louder, series) == ["auto_silence"]
    moved = series_settings.layout_of(ops.set_track(_show(), "t2", gain_db=3.0))
    assert series_settings.differences({**same, "layout": moved}, series) == ["layout"]
    # A section the series does not hold is not a difference.
    assert series_settings.differences(same, {"layout": layout}) == []


def test_extra_tracks_in_the_episode_are_not_a_difference():
    layout = series_settings.layout_of(_show())
    guest = series_settings.layout_of(ops.add_track(_show(), "g", "Guest"))
    assert series_settings.differences({"layout": guest}, {"layout": layout}) == []
    fewer = series_settings.layout_of(ops.delete_track(_show(), "t3"))
    differs = series_settings.differences({"layout": fewer}, {"layout": layout})
    assert differs == ["layout"]


def test_link_record_round_trips_through_the_project():
    p = series_settings.link(Project(), "0190-id", "Vikasietotila", {"automix": {}})
    assert p.series == {"id": "0190-id", "name": "Vikasietotila",
                        "settings": {"automix": series_settings.automix_values({})}}
    again = Project.from_json(p.to_json())
    assert again.series == p.series
    assert "series" not in Project().to_dict()  # an old project keeps its bytes
    assert series_settings.unlink(p).series == {}
