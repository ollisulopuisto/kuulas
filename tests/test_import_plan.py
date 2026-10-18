"""Tests for import placement planning."""

from __future__ import annotations

import pytest

from kuulas.import_plan import ImportItem, Placement, plan_import
from kuulas.messages import KuulasError, set_language

RATE = 48_000
TWO_SECONDS = 2 * RATE


def _item(name: str, frames: int, *, channels: int = 1,
          time_ref_flicks: int | None = None, person: str | None = None) -> ImportItem:
    return ImportItem(name, frames, channels, time_ref_flicks, person)


class TestSideBySide:
    def test_one_item_starts_at_start_frame(self):
        item = _item("take.wav", RATE)
        result = plan_import([item], RATE, mode="side_by_side", start_frame=100)
        assert result == (
            Placement(item, "t0", "take", "speech", 100, True),
        )

    def test_stereo_alone_is_not_music(self):
        item = _item("bed.wav", RATE, channels=2)
        result = plan_import([item], RATE, mode="side_by_side")
        assert result[0].kind == "speech"

    @pytest.mark.parametrize(
        "name", ["Music bed.wav", "taustamusiikki.wav", "Jingle_2.wav"])
    def test_a_music_name_is_music(self, name):
        result = plan_import([_item(name, RATE, channels=1)], RATE, mode="side_by_side")
        assert result[0].kind == "music"

    def test_two_time_refs_two_seconds_apart(self):
        earliest = _item("a.wav", RATE, time_ref_flicks=0)
        later = _item("b.wav", RATE, time_ref_flicks=2 * 705_600_000)
        result = plan_import([earliest, later], RATE, mode="side_by_side")
        assert result[0].start_frame == 0
        assert result[1].start_frame == TWO_SECONDS

    def test_no_reference_starts_at_start_frame(self):
        ref = _item("a.wav", RATE, time_ref_flicks=0)
        no_ref = _item("b.wav", RATE, time_ref_flicks=None)
        result = plan_import([ref, no_ref], RATE, mode="side_by_side", start_frame=480)
        assert result[0].start_frame == 480
        assert result[1].start_frame == 480

    def test_order_by_name_is_case_insensitive_natural(self):
        z = _item("take10.wav", RATE)
        a = _item("abc.wav", RATE)
        two = _item("take2.wav", RATE)
        result = plan_import([z, a, two], RATE, mode="side_by_side", order="name")
        assert [p.item.name for p in result] == ["abc.wav", "take2.wav", "take10.wav"]

    def test_order_by_time_puts_missing_last_ties_by_name(self):
        b = _item("b.wav", RATE, time_ref_flicks=200)
        a = _item("a.wav", RATE, time_ref_flicks=100)
        none = _item("c.wav", RATE, time_ref_flicks=None)
        result = plan_import([b, none, a], RATE, mode="side_by_side", order="time")
        assert [p.item.name for p in result] == ["a.wav", "b.wav", "c.wav"]

    def test_track_naming_uses_person_when_set(self):
        anna = _item("rec1.wav", RATE, person="Anna")
        no_one = _item("rec2.wav", RATE)
        result = plan_import([anna, no_one], RATE, mode="side_by_side",
                             track_naming="person")
        assert result[0].track_name == "Anna"
        assert result[1].track_name == "rec2"

    def test_file_naming_strips_extension(self):
        item = _item("my.take.wav", RATE)
        result = plan_import([item], RATE, mode="side_by_side",
                             track_naming="file")
        assert result[0].track_name == "my.take"


class TestSequential:
    def test_one_track_one_clip_after_another(self):
        a = _item("a.wav", RATE)
        b = _item("b.wav", RATE // 2)
        result = plan_import([a, b], RATE, mode="sequential")
        assert result[0].track_key == result[1].track_key
        assert result[0].new_track is True
        assert result[1].new_track is False
        assert result[0].start_frame == 0
        assert result[1].start_frame == RATE

    def test_track_named_after_first_item(self):
        first = _item("intro.wav", RATE)
        second = _item("main.wav", RATE)
        result = plan_import([first, second], RATE, mode="sequential")
        assert result[0].track_name == "intro"
        assert result[1].track_name == "intro"

    def test_respects_ordering_before_sequencing(self):
        b = _item("b.wav", RATE)
        a = _item("a.wav", RATE)
        result = plan_import([b, a], RATE, mode="sequential", order="name")
        assert [p.item.name for p in result] == ["a.wav", "b.wav"]


class TestEquivalenceWithImportMediaDocstring:
    def test_typical_batch_mirrors_session_import_media(self):
        """The docstring of ``Session.import_media`` says:

        - clips are placed by BWF time reference relative to the earliest;
        - a file without one starts at 0;
        - a music-named file is music, anything else is speech.
        """
        with_ref_late = _item("late.wav", RATE, time_ref_flicks=3 * 705_600_000)
        no_ref = _item("phone.wav", RATE)
        with_ref_early = _item("early.wav", RATE, time_ref_flicks=1 * 705_600_000)
        stereo = _item("music.wav", RATE, channels=2)
        result = plan_import(
            [with_ref_late, no_ref, with_ref_early, stereo],
            RATE,
            mode="side_by_side",
        )
        by_name = {p.item.name: p for p in result}
        assert by_name["early.wav"].start_frame == 0
        assert by_name["late.wav"].start_frame == 2 * RATE
        assert by_name["phone.wav"].start_frame == 0
        assert by_name["music.wav"].kind == "music"
        assert by_name["phone.wav"].kind == "speech"


class TestErrors:
    def test_unknown_mode(self):
        with pytest.raises(KuulasError):
            plan_import([], RATE, mode="stacked")

    def test_unknown_order(self):
        with pytest.raises(KuulasError):
            plan_import([], RATE, order="random")

    def test_unknown_track_naming(self):
        with pytest.raises(KuulasError):
            plan_import([], RATE, track_naming="date")

    def test_error_messages_are_translated(self):
        set_language("fi")
        with pytest.raises(KuulasError) as exc_info:
            plan_import([], RATE, mode="stacked")
        text = str(exc_info.value)
        assert text != "error.import_plan.bad_mode"
        assert "stacked" in text


def test_sequential_track_has_one_kind_from_the_first_file():
    items = [ImportItem("a.wav", 100, 1), ImportItem("b.wav", 100, 2)]
    plan = plan_import(items, 48000, mode="sequential")
    assert {p.kind for p in plan} == {"speech"}
