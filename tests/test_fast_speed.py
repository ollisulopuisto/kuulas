"""Tests for fast listening speed state (WP26): a toggle, and a stepless
chosen speed from 1.0x to 2.0x in 0.05x steps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kuulas.fast_speed import (
    MAX_FAST,
    MIN_FAST,
    STEP,
    FastState,
    chip_text,
    effective,
    reset,
    set_fast,
    step_down,
    step_up,
    toggle,
)
from kuulas.messages import t

CASES = json.loads(
    (Path(__file__).parent.parent / "ui" / "tests" / "fixtures" / "fast-speed-cases.json")
    .read_text(encoding="utf-8"))
OPS = {"toggle": toggle, "up": step_up, "down": step_down, "reset": reset}


@pytest.mark.parametrize("case", CASES["ops"], ids=lambda c: f"{c['state']} {c['op']}")
def test_ui_fast_speed_js_agrees_with_these_cases(case):
    """ui/fast-speed.js must agree: both read fast-speed-cases.json."""
    state = FastState(**case["state"])
    got = (set_fast(state, case["arg"]) if case["op"] == "set"
           else OPS[case["op"]](state))
    assert got == FastState(**case["result"])


class TestEffective:
    def test_inactive_is_normal_speed(self):
        assert effective(FastState(fast=1.5, active=False)) == 1.0

    def test_active_uses_the_chosen_speed(self):
        assert effective(FastState(fast=1.35, active=True)) == 1.35


class TestToggle:
    def test_turns_on_and_off_keeping_the_chosen_speed(self):
        on = toggle(FastState(fast=1.35, active=False))
        assert on == FastState(fast=1.35, active=True)
        assert toggle(on) == FastState(fast=1.35, active=False)

    def test_on_at_a_chosen_1_0_uses_the_default(self):
        assert toggle(FastState(fast=1.0, active=False)) == FastState(1.5, True)


class TestSteps:
    def test_a_step_is_five_hundredths(self):
        assert STEP == 0.05
        assert step_up(FastState(fast=1.5)).fast == 1.55
        assert step_down(FastState(fast=1.5)).fast == 1.45

    def test_clamped_at_both_ends(self):
        assert step_up(FastState(fast=MAX_FAST)).fast == MAX_FAST
        assert step_down(FastState(fast=MIN_FAST)).fast == MIN_FAST

    def test_a_step_does_not_switch_it_on_or_off(self):
        assert step_up(FastState(fast=1.5, active=False)).active is False
        assert step_down(FastState(fast=1.5, active=True)).active is True

    def test_the_whole_range_in_twenty_steps_without_drift(self):
        state = FastState(fast=MIN_FAST)
        seen = [state.fast]
        for _ in range(20):
            state = step_up(state)
            seen.append(state.fast)
        assert seen == [round(1.0 + 0.05 * i, 2) for i in range(21)]
        for _ in range(20):
            state = step_down(state)
        assert state.fast == MIN_FAST


class TestSetFast:
    def test_snaps_to_the_step_and_clamps(self):
        state = FastState(fast=1.5, active=True)
        assert set_fast(state, 5.0) == FastState(fast=2.0, active=True)
        assert set_fast(state, 0.5) == FastState(fast=1.0, active=True)
        assert set_fast(state, 1.23).fast == 1.25
        assert set_fast(state, 1.37).fast == 1.35


class TestReset:
    def test_back_to_normal(self):
        assert reset(FastState(fast=1.8, active=True)) == FastState(1.0, False)


class TestChipText:
    def test_empty_at_normal_speed(self):
        assert chip_text(FastState(fast=1.5, active=False), "en") == ""

    def test_empty_when_fast_is_one(self):
        assert chip_text(FastState(fast=1.0, active=True), "en") == ""

    def test_english_uses_decimal_point(self):
        assert chip_text(FastState(fast=1.5, active=True), "en") \
            == "1.5×"  # noqa: RUF001 - multiplication sign is intentional

    def test_exact_to_the_step(self):
        assert chip_text(FastState(fast=1.35, active=True), "en") == "1.35×"  # noqa: RUF001
        assert chip_text(FastState(fast=2.0, active=True), "en") == "2×"  # noqa: RUF001

    def test_finnish_uses_decimal_comma(self):
        assert chip_text(FastState(fast=1.5, active=True), "fi") == "1,5×"  # noqa: RUF001
        assert chip_text(FastState(fast=1.35, active=True), "fi") == "1,35×"  # noqa: RUF001

    def test_unit_key_is_translated(self):
        # The unit suffix is read from the locale; this checks the key exists.
        assert t("format.speed", value="2.0") == "2.0×"  # noqa: RUF001
        assert t("format.speed", value="2,0") == "2,0×"  # noqa: RUF001
