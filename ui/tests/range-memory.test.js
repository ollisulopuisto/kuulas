import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { rememberRange, stepRangeMemory } from "../range-memory.js";

const marks = { inPoint: 100, outPoint: 500, rangeTracks: new Set(["A"]) };
const none = { inPoint: null, outPoint: null };

describe("the range a cut used up comes back on Undo", () => {
  test("nothing remembered, nothing happens", () => {
    assert.deepEqual(stepRangeMemory(null, "h1", none), { memory: null, patch: null });
  });

  test("the edit applies (head moves on): remembered, no patch", () => {
    const memory = rememberRange("h1", marks);
    const step = stepRangeMemory(memory, "h2", none);
    assert.equal(step.patch, null);
    assert.equal(step.memory.after, "h2");
  });

  test("Undo back to the head before the cut restores in, out and the lanes", () => {
    const applied = stepRangeMemory(rememberRange("h1", marks), "h2", none).memory;
    const undone = stepRangeMemory(applied, "h1", none);
    assert.deepEqual(undone.patch, {
      inPoint: 100,
      outPoint: 500,
      rangeTracks: new Set(["A"]),
    });
    assert.deepEqual(undone.memory, applied);
  });

  test("Redo clears the marks again, and Undo restores them once more", () => {
    const applied = stepRangeMemory(rememberRange("h1", marks), "h2", none).memory;
    const redone = stepRangeMemory(applied, "h2", marks);
    assert.deepEqual(redone.patch, {
      inPoint: null,
      outPoint: null,
      rangeTracks: new Set(),
      selection: new Set(),
    });
  });

  test("marks the user has set meanwhile are not overwritten by an Undo", () => {
    const applied = stepRangeMemory(rememberRange("h1", marks), "h2", none).memory;
    const undone = stepRangeMemory(applied, "h1", { inPoint: 7, outPoint: null });
    assert.equal(undone.patch, null);
  });

  test("any other edit forgets the memory", () => {
    const applied = stepRangeMemory(rememberRange("h1", marks), "h2", none).memory;
    assert.deepEqual(stepRangeMemory(applied, "h9", none), { memory: null, patch: null });
  });
});
