"""Tests for the bus tree utilities."""

from __future__ import annotations

import pytest

from kuulas.bus_tree import (
    badges,
    check_parent,
    children,
    depth,
    descendants,
    effective_gain_db,
    effective_mute,
)


def bus(bus_id: str, parent: str | None = None, *, mute: bool = False,
        gain_db: float = 0.0) -> dict[str, object]:
    return {"id": bus_id, "parent": parent, "mute": mute, "gain_db": gain_db}


class TestDepth:
    def test_top_level_is_one(self):
        buses = [bus("a"), bus("b")]
        assert depth(buses, "a") == 1
        assert depth(buses, "b") == 1

    def test_child_is_two(self):
        buses = [bus("a"), bus("b", parent="a")]
        assert depth(buses, "b") == 2

    def test_grandchild_is_three(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="b")]
        assert depth(buses, "c") == 3

    def test_unknown_id_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            depth([bus("a")], "missing")

    def test_cycle_raises(self):
        buses = [bus("a", parent="b"), bus("b", parent="a")]
        with pytest.raises(ValueError, match="cycle"):
            depth(buses, "a")

    def test_self_parent_cycle_raises(self):
        with pytest.raises(ValueError, match="cycle"):
            depth([bus("a", parent="a")], "a")


class TestCheckParent:
    def test_none_parent_always_allowed(self):
        buses = [bus("a", parent="b"), bus("b")]
        assert check_parent(buses, "a", None) is None

    def test_allows_existing_parent(self):
        buses = [bus("a"), bus("b", parent="a")]
        assert check_parent(buses, "b", "a") is None

    def test_self_parent_refused(self):
        buses = [bus("a"), bus("b", parent="a")]
        with pytest.raises(ValueError, match="cycle"):
            check_parent(buses, "b", "b")

    def test_cycle_to_descendant_refused(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="b")]
        with pytest.raises(ValueError, match="cycle"):
            check_parent(buses, "a", "c")

    def test_unknown_parent_refused(self):
        with pytest.raises(ValueError, match="unknown"):
            check_parent([bus("a")], "a", "missing")

    def test_unknown_bus_refused(self):
        with pytest.raises(ValueError, match="unknown"):
            check_parent([bus("a")], "missing", None)

    def test_depth_four_refused_with_default_max_depth(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="b"), bus("d")]
        with pytest.raises(ValueError, match="depth"):
            check_parent(buses, "d", "c")

    def test_depth_four_allowed_with_max_depth_four(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="b"), bus("d")]
        assert check_parent(buses, "d", "c", max_depth=4) is None

    def test_descendant_depth_exceeds_max_depth(self):
        buses = [
            bus("a"),
            bus("b", parent="a"),
            bus("c", parent="b"),
            bus("d", parent="c"),
        ]
        with pytest.raises(ValueError, match="depth"):
            check_parent(buses, "b", "a", max_depth=3)

    def test_max_depth_allows_exactly_limit(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="b")]
        assert check_parent(buses, "c", "b", max_depth=3) is None


class TestBadges:
    def test_top_level_letters(self):
        buses = [bus("a"), bus("b"), bus("c")]
        assert badges(buses) == {"a": "A", "b": "B", "c": "C"}

    def test_children_numbers(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="a")]
        assert badges(buses) == {"a": "A", "b": "A1", "c": "A2"}

    def test_grandchildren_lowercase_letters(self):
        buses = [
            bus("a"),
            bus("b", parent="a"),
            bus("c", parent="b"),
            bus("d", parent="b"),
        ]
        assert badges(buses) == {
            "a": "A",
            "b": "A1",
            "c": "A1a",
            "d": "A1b",
        }

    def test_multiple_top_level_with_children(self):
        buses = [
            bus("a"),
            bus("b", parent="a"),
            bus("c"),
            bus("d", parent="c"),
            bus("e", parent="c"),
        ]
        assert badges(buses) == {
            "a": "A",
            "b": "A1",
            "c": "B",
            "d": "B1",
            "e": "B2",
        }

    def test_list_order_decides_sibling_order(self):
        buses = [bus("a"), bus("x", parent="a"), bus("y", parent="a")]
        result = badges(buses)
        assert result["x"] == "A1"
        assert result["y"] == "A2"
        # Swap order
        buses = [bus("a"), bus("y", parent="a"), bus("x", parent="a")]
        result = badges(buses)
        assert result["y"] == "A1"
        assert result["x"] == "A2"

    def test_badges_past_z(self):
        buses = [bus(f"b{i}") for i in range(28)]
        result = badges(buses)
        assert result["b0"] == "A"
        assert result["b25"] == "Z"
        assert result["b26"] == "AA"
        assert result["b27"] == "AB"

    def test_child_before_parent_in_list_gets_badge(self):
        buses = [bus("b", parent="a"), bus("a")]
        assert badges(buses) == {"a": "A", "b": "A1"}


class TestEffectiveMute:
    def test_unmuted_is_false(self):
        buses = [bus("a"), bus("b", parent="a")]
        assert effective_mute(buses, "b") is False

    def test_self_muted_is_true(self):
        buses = [bus("a"), bus("b", parent="a", mute=True)]
        assert effective_mute(buses, "b") is True

    def test_ancestor_muted_is_true(self):
        buses = [bus("a", mute=True), bus("b", parent="a"), bus("c", parent="b")]
        assert effective_mute(buses, "c") is True

    def test_mute_cascade_through_three_levels(self):
        buses = [
            bus("a"),
            bus("b", parent="a"),
            bus("c", parent="b"),
            bus("d", parent="c", mute=True),
        ]
        assert effective_mute(buses, "d") is True
        assert effective_mute(buses, "c") is False


class TestEffectiveGain:
    def test_gain_without_ancestors(self):
        buses = [bus("a", gain_db=2.5)]
        assert effective_gain_db(buses, "a") == 2.5

    def test_gain_sums_ancestors(self):
        buses = [
            bus("a", gain_db=1.0),
            bus("b", parent="a", gain_db=2.0),
            bus("c", parent="b", gain_db=3.0),
        ]
        assert effective_gain_db(buses, "c") == 6.0

    def test_gain_cascade_through_three_levels(self):
        buses = [
            bus("a", gain_db=-1.5),
            bus("b", parent="a", gain_db=2.0),
            bus("c", parent="b", gain_db=0.5),
        ]
        assert effective_gain_db(buses, "c") == 1.0


class TestChildren:
    def test_direct_children_in_list_order(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="a")]
        assert children(buses, "a") == ("b", "c")

    def test_children_excludes_grandchildren(self):
        buses = [bus("a"), bus("b", parent="a"), bus("c", parent="b")]
        assert children(buses, "a") == ("b",)

    def test_no_children_returns_empty(self):
        assert children([bus("a")], "a") == ()


class TestDescendants:
    def test_descendants_depth_first(self):
        buses = [
            bus("a"),
            bus("b", parent="a"),
            bus("c", parent="b"),
            bus("d", parent="a"),
        ]
        assert descendants(buses, "a") == ("b", "c", "d")

    def test_descendants_order_follows_list_order(self):
        buses = [
            bus("a"),
            bus("d", parent="a"),
            bus("b", parent="a"),
            bus("c", parent="b"),
        ]
        assert descendants(buses, "a") == ("d", "b", "c")

    def test_no_descendants_returns_empty(self):
        assert descendants([bus("a")], "a") == ()
