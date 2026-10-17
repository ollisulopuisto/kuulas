"""Tests for fast listening speed state."""

from __future__ import annotations

from kuulas.fast_speed import (
    FastState,
    chip_text,
    effective,
    set_fast,
    step_down,
    step_up,
    toggle,
)
from kuulas.messages import t


class TestEffective:
    def test_inactive_is_normal_speed(self):
        state = FastState(fast=1.5, active=False)
        assert effective(state) == 1.0

    def test_active_uses_fast_speed(self):
        state = FastState(fast=1.5, active=True)
        assert effective(state) == 1.5


class TestToggle:
    def test_turns_on(self):
        state = FastState(fast=1.5, active=False)
        assert toggle(state) == FastState(fast=1.5, active=True)

    def test_turns_off(self):
        state = FastState(fast=1.5, active=True)
        assert toggle(state) == FastState(fast=1.5, active=False)


class TestStepUp:
    def test_increments_by_tenth(self):
        state = FastState(fast=1.5, active=True)
        assert step_up(state).fast == 1.6

    def test_clamps_at_top(self):
        state = FastState(fast=3.0, active=True)
        assert step_up(state).fast == 3.0


class TestStepDown:
    def test_decrements_by_tenth(self):
        state = FastState(fast=1.5, active=True)
        assert step_down(state).fast == 1.4

    def test_clamps_at_bottom(self):
        state = FastState(fast=1.1, active=True)
        assert step_down(state).fast == 1.1


class TestDrift:
    def test_repeated_steps_do_not_drift(self):
        state = FastState(fast=1.1, active=True)
        for _ in range(3):
            state = step_up(state)
        assert state.fast == 1.4


class TestSetFast:
    def test_clamps_and_rounds(self):
        state = FastState(fast=1.5, active=True)
        assert set_fast(state, 5.0) == FastState(fast=3.0, active=True)
        assert set_fast(state, 0.5) == FastState(fast=1.1, active=True)
        assert set_fast(state, 1.25).fast == 1.3


class TestChipText:
    def test_empty_at_normal_speed(self):
        assert chip_text(FastState(fast=1.5, active=False), "en") == ""

    def test_empty_when_fast_is_one(self):
        assert chip_text(FastState(fast=1.0, active=True), "en") == ""

    def test_english_uses_decimal_point(self):
        assert chip_text(FastState(fast=1.5, active=True), "en") \
            == "1.5×"  # noqa: RUF001 - multiplication sign is intentional

    def test_finnish_uses_decimal_comma(self):
        assert chip_text(FastState(fast=1.5, active=True), "fi") == "1,5×"  # noqa: RUF001

    def test_unit_key_is_translated(self):
        # The unit suffix is read from the locale; this checks the key exists.
        assert t("format.speed", value="2.0") == "2.0×"  # noqa: RUF001
        assert t("format.speed", value="2,0") == "2,0×"  # noqa: RUF001
