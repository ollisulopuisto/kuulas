import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { DELAY_MS, INITIAL_TIP, placeTip, tipReduce, tipText } from "../tip-model.js";

describe("tipReduce", () => {
  test("constants", () => {
    assert.equal(DELAY_MS, 600);
    assert.deepEqual(INITIAL_TIP, {
      phase: "idle",
      target: null,
      since: 0,
      suppressed: null,
    });
  });

  test("the full enter/tick/leave cycle", () => {
    // 1. Enter target A at t=1000
    const s1 = tipReduce(INITIAL_TIP, {
      type: "enter",
      target: "btn-cut",
      now: 1000,
    });
    assert.deepEqual(s1, {
      phase: "pending",
      target: "btn-cut",
      since: 1000,
      suppressed: null,
    });

    // 2. Tick after delay (t=1600) -> shown
    const s2 = tipReduce(s1, { type: "tick", now: 1600 });
    assert.deepEqual(s2, {
      phase: "shown",
      target: "btn-cut",
      since: 1000,
      suppressed: null,
    });

    // 3. Leave target A -> idle
    const s3 = tipReduce(s2, {
      type: "leave",
      target: "btn-cut",
      now: 2000,
    });
    assert.deepEqual(s3, {
      phase: "idle",
      target: null,
      since: 2000,
      suppressed: null,
    });
  });

  test("tick before the delay does nothing", () => {
    const s1 = tipReduce(INITIAL_TIP, {
      type: "enter",
      target: "btn-cut",
      now: 1000,
    });
    const s2 = tipReduce(s1, { type: "tick", now: 1599 });
    assert.equal(s2.phase, "pending");
    assert.equal(s2.target, "btn-cut");
  });

  test("press suppresses until leave", () => {
    const s1 = tipReduce(INITIAL_TIP, {
      type: "enter",
      target: "btn-cut",
      now: 1000,
    });
    const s2 = tipReduce(s1, { type: "tick", now: 1600 });
    assert.equal(s2.phase, "shown");

    // Press target
    const s3 = tipReduce(s2, {
      type: "press",
      target: "btn-cut",
      now: 1700,
    });
    assert.deepEqual(s3, {
      phase: "idle",
      target: null,
      since: 1700,
      suppressed: "btn-cut",
    });

    // Re-enter while still suppressed: does not pop up / remains suppressed
    const s4 = tipReduce(s3, {
      type: "enter",
      target: "btn-cut",
      now: 1800,
    });
    assert.equal(s4.phase, "idle");
    assert.equal(s4.suppressed, "btn-cut");

    // Leave clears suppression
    const s5 = tipReduce(s4, {
      type: "leave",
      target: "btn-cut",
      now: 1900,
    });
    assert.equal(s5.phase, "idle");
    assert.equal(s5.suppressed, null);

    // Re-enter after leave: enters pending normally
    const s6 = tipReduce(s5, {
      type: "enter",
      target: "btn-cut",
      now: 2000,
    });
    assert.equal(s6.phase, "pending");
    assert.equal(s6.target, "btn-cut");
  });

  test("moving between targets while shown has no delay", () => {
    const s1 = {
      phase: "shown",
      target: "btn-cut",
      since: 1000,
      suppressed: null,
    };
    const s2 = tipReduce(s1, {
      type: "enter",
      target: "btn-copy",
      now: 1800,
    });
    assert.deepEqual(s2, {
      phase: "shown",
      target: "btn-copy",
      since: 1800,
      suppressed: null,
    });
  });

  test("immutability of the input state", () => {
    const state = Object.freeze({
      phase: "pending",
      target: "btn-cut",
      since: 1000,
      suppressed: null,
    });
    const next = tipReduce(state, { type: "tick", now: 1650 });
    assert.notEqual(state, next);
    assert.equal(next.phase, "shown");
    assert.equal(state.phase, "pending");
  });
});

describe("tipText", () => {
  test("returns hint alone when keys is empty or missing", () => {
    assert.equal(tipText("Cut"), "Cut");
    assert.equal(tipText("Cut", []), "Cut");
    assert.equal(tipText("  Cut  "), "Cut");
    assert.equal(tipText("  Cut  ", null), "Cut");
  });

  test("appends formatted keys when present", () => {
    assert.equal(tipText("Cut", ["Cmd+X"]), "Cut (Cmd+X)");
    assert.equal(tipText("Cut", ["Cmd+X", "Shift+Del"]), "Cut (Cmd+X, Shift+Del)");
    assert.equal(tipText("  Split at cursor  ", ["S"]), "Split at cursor (S)");
  });

  test("returns empty string when hint is empty or not a string", () => {
    assert.equal(tipText(""), "");
    assert.equal(tipText("   "), "");
    assert.equal(tipText(null), "");
    assert.equal(tipText(undefined), "");
  });
});

describe("placeTip", () => {
  const viewport = { width: 1000, height: 800 };
  const size = { width: 120, height: 32 };

  test("placement below: centred horizontally and placed below anchor with gap", () => {
    const anchor = { x: 200, y: 100, width: 40, height: 30 };
    // center X = 200 + (40 - 120) / 2 = 160
    // below Y = 100 + 30 + 6 = 136
    assert.deepEqual(placeTip(anchor, size, viewport, 6), {
      x: 160,
      y: 136,
      side: "below",
    });
  });

  test("flipped above when tip would not fit below viewport", () => {
    const anchor = { x: 200, y: 760, width: 40, height: 30 };
    // below Y = 760 + 30 + 6 = 796 -> 796 + 32 = 828 > 800 - 6
    // above Y = 760 - 32 - 6 = 722
    assert.deepEqual(placeTip(anchor, size, viewport, 6), {
      x: 160,
      y: 722,
      side: "above",
    });
  });

  test("clamped left edge respects gap", () => {
    const anchor = { x: 10, y: 100, width: 20, height: 30 };
    // center X = 10 + (20 - 120) / 2 = -40 -> clamped to gap 6
    assert.deepEqual(placeTip(anchor, size, viewport, 6), {
      x: 6,
      y: 136,
      side: "below",
    });
  });

  test("clamped right edge respects gap", () => {
    const anchor = { x: 960, y: 100, width: 30, height: 30 };
    // center X = 960 + (30 - 120) / 2 = 915 -> max is 1000 - 120 - 6 = 874
    assert.deepEqual(placeTip(anchor, size, viewport, 6), {
      x: 874,
      y: 136,
      side: "below",
    });
  });
});
