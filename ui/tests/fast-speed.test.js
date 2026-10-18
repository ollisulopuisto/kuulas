import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import {
  chipFast,
  dragSpeed,
  effective,
  fromStored,
  MAX_FAST,
  MIN_FAST,
  PX_PER_STEP,
  reset,
  STEP,
  setFast,
  stepDown,
  stepUp,
  toggle,
} from "../fast-speed.js";

// The same cases tests/test_fast_speed.py reads: this must match fast_speed.py.
const cases = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/fast-speed-cases.json", import.meta.url)), "utf8"),
);
const ops = { toggle, up: stepUp, down: stepDown, reset };

describe("fast listening agrees with fast_speed.py", () => {
  for (const c of cases.ops) {
    test(`${JSON.stringify(c.state)} ${c.op}${c.arg === undefined ? "" : ` ${c.arg}`}`, () => {
      const got = c.op === "set" ? setFast(c.state, c.arg) : ops[c.op](c.state);
      assert.deepEqual(got, c.result);
    });
  }
});

describe("the toggle state machine", () => {
  test("on and off keep the chosen speed; the effective speed follows", () => {
    const off = { fast: 1.35, active: false };
    assert.equal(effective(off), 1);
    const on = toggle(off);
    assert.deepEqual(on, { fast: 1.35, active: true });
    assert.equal(effective(on), 1.35);
    assert.deepEqual(toggle(on), off);
  });
  test("nudging changes only the chosen speed, never on or off", () => {
    assert.equal(stepUp({ fast: 1.5, active: false }).active, false);
    assert.equal(stepDown({ fast: 1.5, active: true }).active, true);
  });
  test("twenty steps cover the range exactly", () => {
    let state = { fast: MIN_FAST, active: true };
    for (let i = 0; i < 20; i++) state = stepUp(state);
    assert.equal(state.fast, MAX_FAST);
    state = stepUp(state);
    assert.equal(state.fast, MAX_FAST);
    for (let i = 0; i < 20; i++) state = stepDown(state);
    assert.equal(state.fast, MIN_FAST);
    assert.equal(STEP, 0.05);
  });
});

describe("what is remembered", () => {
  test("a stored state comes back, snapped and clamped", () => {
    assert.deepEqual(fromStored({ fast: 1.37, active: true }), { fast: 1.35, active: true });
    assert.deepEqual(fromStored({ fast: 9, active: false }), { fast: 2, active: false });
  });
  test("garbage is the default", () => {
    for (const bad of [null, undefined, "x", 3, { fast: "fast" }]) {
      assert.deepEqual(fromStored(bad), { fast: 1.5, active: false });
    }
  });
});

describe("the chip", () => {
  const format = (v, { digits }) => v.toFixed(digits);
  test("hidden when off or at 1.0", () => {
    assert.equal(chipFast({ fast: 1.5, active: false }, format), null);
    assert.equal(chipFast({ fast: 1, active: true }, format), null);
  });
  test("exact to the step, without trailing zeros", () => {
    assert.equal(chipFast({ fast: 1.35, active: true }, format), "1.35");
    assert.equal(chipFast({ fast: 1.5, active: true }, format), "1.5");
    assert.equal(chipFast({ fast: 2, active: true }, format), "2");
  });
});

describe("dragging the speed display (owner, 2026-10-18)", () => {
  test("every PX_PER_STEP pixels to the right is one step faster, to the left slower", () => {
    assert.equal(dragSpeed(1.5, PX_PER_STEP), 1.55);
    assert.equal(dragSpeed(1.5, -5 * PX_PER_STEP), 1.25);
    assert.equal(dragSpeed(1.5, 0), 1.5);
  });
  test("a part of a step rounds to the nearest step, with no float dust", () => {
    assert.equal(dragSpeed(1.35, PX_PER_STEP * 0.4), 1.35);
    assert.equal(dragSpeed(1.35, PX_PER_STEP * 0.6), 1.4);
  });
  test("stays within 1.0 and 2.0", () => {
    assert.equal(dragSpeed(1.9, 100 * PX_PER_STEP), MAX_FAST);
    assert.equal(dragSpeed(1.1, -100 * PX_PER_STEP), MIN_FAST);
  });
});
