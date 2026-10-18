import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { isReordered, moveBlock, moveToIndex, moveTrack } from "../track-order.js";

describe("moveTrack", () => {
  test("moves track by positive and negative delta", () => {
    const order = ["a", "b", "c", "d"];
    assert.deepEqual(moveTrack(order, "b", 1), ["a", "c", "b", "d"]);
    assert.deepEqual(moveTrack(order, "c", -1), ["a", "c", "b", "d"]);
  });

  test("clamps at both ends", () => {
    const order = ["a", "b", "c", "d"];
    assert.deepEqual(moveTrack(order, "a", -10), ["a", "b", "c", "d"]);
    assert.deepEqual(moveTrack(order, "b", -10), ["b", "a", "c", "d"]);
    assert.deepEqual(moveTrack(order, "d", 10), ["a", "b", "c", "d"]);
    assert.deepEqual(moveTrack(order, "c", 10), ["a", "b", "d", "c"]);
  });

  test("throws Error for unknown track id", () => {
    const order = ["a", "b"];
    assert.throws(() => moveTrack(order, "unknown", 1), /unknown/i);
  });

  test("does not mutate original array", () => {
    const order = Object.freeze(["a", "b", "c"]);
    const res = moveTrack(order, "a", 1);
    assert.deepEqual(order, ["a", "b", "c"]);
    assert.deepEqual(res, ["b", "a", "c"]);
  });
});

describe("moveToIndex", () => {
  test("moves track to specified index", () => {
    const order = ["a", "b", "c", "d"];
    assert.deepEqual(moveToIndex(order, "a", 2), ["b", "c", "a", "d"]);
    assert.deepEqual(moveToIndex(order, "d", 0), ["d", "a", "b", "c"]);
    assert.deepEqual(moveToIndex(order, "b", 1), ["a", "b", "c", "d"]);
  });

  test("clamps index to 0..length-1", () => {
    const order = ["a", "b", "c", "d"];
    assert.deepEqual(moveToIndex(order, "c", -5), ["c", "a", "b", "d"]);
    assert.deepEqual(moveToIndex(order, "b", 99), ["a", "c", "d", "b"]);
  });

  test("throws Error for unknown track id", () => {
    const order = ["a", "b"];
    assert.throws(() => moveToIndex(order, "x", 0), /unknown/i);
  });

  test("does not mutate original array", () => {
    const order = Object.freeze(["a", "b", "c"]);
    const res = moveToIndex(order, "c", 0);
    assert.deepEqual(order, ["a", "b", "c"]);
    assert.deepEqual(res, ["c", "a", "b"]);
  });
});

describe("moveBlock", () => {
  test("moves consecutive ids together by delta", () => {
    const order = ["a", "b", "c", "d", "e"];
    assert.deepEqual(moveBlock(order, ["b", "c"], 1), ["a", "d", "b", "c", "e"]);
    assert.deepEqual(moveBlock(order, ["c", "d"], -1), ["a", "c", "d", "b", "e"]);
  });

  test("moves non-consecutive ids keeping their relative order", () => {
    const order = ["a", "b", "c", "d", "e"];
    assert.deepEqual(moveBlock(order, ["b", "d"], 1), ["a", "c", "b", "e", "d"]);
    assert.deepEqual(moveBlock(order, ["b", "d"], -1), ["b", "a", "d", "c", "e"]);
  });

  test("blocked as a whole at start (index 0)", () => {
    const order = ["a", "b", "c", "d", "e"];
    assert.deepEqual(moveBlock(order, ["a", "c"], -1), ["a", "b", "c", "d", "e"]);
    assert.deepEqual(moveBlock(order, ["b", "d"], -5), ["b", "a", "d", "c", "e"]);
  });

  test("blocked as a whole at end (length - 1)", () => {
    const order = ["a", "b", "c", "d", "e"];
    assert.deepEqual(moveBlock(order, ["c", "e"], 1), ["a", "b", "c", "d", "e"]);
    assert.deepEqual(moveBlock(order, ["b", "d"], 5), ["a", "c", "b", "e", "d"]);
  });

  test("ignores ids not in order, empty ids returns a copy", () => {
    const order = ["a", "b", "c"];
    assert.deepEqual(moveBlock(order, [], 1), ["a", "b", "c"]);
    assert.deepEqual(moveBlock(order, ["x", "y"], 1), ["a", "b", "c"]);
    assert.deepEqual(moveBlock(order, ["a", "x"], 1), ["b", "a", "c"]);
  });

  test("does not mutate original array or ids", () => {
    const order = Object.freeze(["a", "b", "c", "d"]);
    const ids = Object.freeze(["b", "c"]);
    const res = moveBlock(order, ids, 1);
    assert.deepEqual(order, ["a", "b", "c", "d"]);
    assert.deepEqual(res, ["a", "d", "b", "c"]);
  });
});

describe("isReordered", () => {
  test("returns false when arrays have identical order", () => {
    assert.equal(isReordered(["a", "b", "c"], ["a", "b", "c"]), false);
    assert.equal(isReordered([], []), false);
  });

  test("returns true when order differs or lengths differ", () => {
    assert.equal(isReordered(["a", "b"], ["b", "a"]), true);
    assert.equal(isReordered(["a", "b"], ["a", "b", "c"]), true);
    assert.equal(isReordered(["a"], []), true);
  });
});
