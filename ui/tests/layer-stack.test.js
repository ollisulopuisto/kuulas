import assert from "node:assert/strict";
import test from "node:test";
import {
  activeLayers,
  addLayer,
  describeTier,
  effectiveStatus,
  moveLayer,
  removeLayer,
  toggleBypass,
} from "../layer-stack.js";

test("addLayer: start, middle, end, clamped index, duplicate id", () => {
  const l1 = { id: "l1", kind: "eq", tier: 1, bypass: false, status: "live" };
  const l2 = { id: "l2", kind: "comp", tier: 1, bypass: false, status: "live" };
  const l3 = {
    id: "l3",
    kind: "denoise",
    tier: 2,
    bypass: false,
    status: "ready",
  };

  // Add to empty stack
  let stack = addLayer([], l1);
  assert.deepEqual(stack, [l1]);

  // Add at end
  stack = addLayer(stack, l2);
  assert.deepEqual(stack, [l1, l2]);

  // Add in middle
  stack = addLayer(stack, l3, 1);
  assert.deepEqual(stack, [l1, l3, l2]);

  // Add at start (index 0)
  const l0 = { id: "l0", kind: "gain", tier: 1, bypass: false, status: "live" };
  stack = addLayer(stack, l0, 0);
  assert.deepEqual(stack, [l0, l1, l3, l2]);

  // Clamped index beyond length
  const lEnd = {
    id: "lEnd",
    kind: "limiter",
    tier: 1,
    bypass: false,
    status: "live",
  };
  const stackEnd = addLayer(stack, lEnd, 999);
  assert.equal(stackEnd[stackEnd.length - 1].id, "lEnd");

  // Clamped negative index
  const lNeg = {
    id: "lNeg",
    kind: "gate",
    tier: 1,
    bypass: false,
    status: "live",
  };
  const stackNeg = addLayer(stack, lNeg, -10);
  assert.equal(stackNeg[0].id, "lNeg");

  // Duplicate id throws Error
  assert.throws(() => addLayer(stack, { id: "l1", kind: "eq" }), /duplicate/i);
});

test("removeLayer: removes layer, unknown id throws", () => {
  const stack = [
    { id: "l1", kind: "eq" },
    { id: "l2", kind: "comp" },
    { id: "l3", kind: "gate" },
  ];

  const removed = removeLayer(stack, "l2");
  assert.deepEqual(removed, [
    { id: "l1", kind: "eq" },
    { id: "l3", kind: "gate" },
  ]);

  // Unknown id throws Error
  assert.throws(() => removeLayer(stack, "nonexistent"), /unknown/i);
});

test("moveLayer: move up, down, clamp at start/end, unknown id throws", () => {
  const stack = [
    { id: "l1", kind: "eq" },
    { id: "l2", kind: "comp" },
    { id: "l3", kind: "gate" },
  ];

  // Move l2 down (+1) -> moves to index 2
  const movedDown = moveLayer(stack, "l2", 1);
  assert.deepEqual(
    movedDown.map((l) => l.id),
    ["l1", "l3", "l2"],
  );

  // Move l2 up (-1) -> moves to index 0
  const movedUp = moveLayer(stack, "l2", -1);
  assert.deepEqual(
    movedUp.map((l) => l.id),
    ["l2", "l1", "l3"],
  );

  // Clamp at end
  const clampedEnd = moveLayer(stack, "l3", 5);
  assert.deepEqual(
    clampedEnd.map((l) => l.id),
    ["l1", "l2", "l3"],
  );

  // Clamp at start
  const clampedStart = moveLayer(stack, "l1", -5);
  assert.deepEqual(
    clampedStart.map((l) => l.id),
    ["l1", "l2", "l3"],
  );

  // Unknown id throws
  assert.throws(() => moveLayer(stack, "unknown", 1), /unknown/i);
});

test("toggleBypass: toggled twice returns equal stack, unknown id throws", () => {
  const stack = [
    { id: "l1", bypass: false, status: "live" },
    { id: "l2", bypass: true, status: "bypassed" },
  ];

  const toggledOnce = toggleBypass(stack, "l1");
  assert.equal(toggledOnce[0].bypass, true);
  assert.equal(toggledOnce[1].bypass, true);

  const toggledTwice = toggleBypass(toggledOnce, "l1");
  assert.deepEqual(toggledTwice, stack);

  // Unknown id throws
  assert.throws(() => toggleBypass(stack, "unknown"), /unknown/i);
});

test("effectiveStatus: with and without bypass", () => {
  const live = { id: "l1", bypass: false, status: "live" };
  const analysing = { id: "l2", bypass: false, status: "analysing" };
  const bypassed = { id: "l3", bypass: true, status: "ready" };

  assert.equal(effectiveStatus(live), "live");
  assert.equal(effectiveStatus(analysing), "analysing");
  assert.equal(effectiveStatus(bypassed), "bypassed");
});

test("activeLayers: order and filtering", () => {
  const stack = [
    { id: "l1", bypass: false },
    { id: "l2", bypass: true },
    { id: "l3", bypass: false },
    { id: "l4", bypass: true },
  ];

  const active = activeLayers(stack);
  assert.deepEqual(active, [
    { id: "l1", bypass: false },
    { id: "l3", bypass: false },
  ]);
});

test("describeTier: 1, 2, 3 and unknown", () => {
  assert.equal(describeTier(1), "real-time");
  assert.equal(describeTier(2), "analyse once");
  assert.equal(describeTier(3), "render");
  assert.equal(describeTier(0), "unknown");
  assert.equal(describeTier(4), "unknown");
  assert.equal(describeTier("foo"), "unknown");
  assert.equal(describeTier(null), "unknown");
});

test("immutability of inputs", () => {
  const layer1 = Object.freeze({
    id: "l1",
    kind: "eq",
    tier: 1,
    bypass: false,
    status: "live",
  });
  const layer2 = Object.freeze({
    id: "l2",
    kind: "comp",
    tier: 1,
    bypass: false,
    status: "live",
  });
  const stack = Object.freeze([layer1, layer2]);

  const afterAdd = addLayer(stack, { id: "l3", kind: "gate" });
  assert.notEqual(afterAdd, stack);
  assert.equal(stack.length, 2);

  const afterRemove = removeLayer(stack, "l1");
  assert.notEqual(afterRemove, stack);
  assert.equal(stack.length, 2);

  const afterMove = moveLayer(stack, "l1", 1);
  assert.notEqual(afterMove, stack);
  assert.equal(stack[0].id, "l1");

  const afterBypass = toggleBypass(stack, "l1");
  assert.notEqual(afterBypass, stack);
  assert.notEqual(afterBypass[0], layer1);
  assert.equal(layer1.bypass, false);
});
