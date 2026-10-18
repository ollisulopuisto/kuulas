import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { addPoint, movePoint, nearestPoint, removePoint } from "../envelope-edit.js";

describe("addPoint", () => {
  test("inserts into an empty envelope", () => {
    const env = addPoint([], 100, -6.0);
    assert.deepEqual(env, [[100, -6.0]]);
  });

  test("inserts in sorted frame order at start, middle, and end", () => {
    let env = [[100, 0]];
    env = addPoint(env, 50, -3);
    assert.deepEqual(env, [
      [50, -3],
      [100, 0],
    ]);

    env = addPoint(env, 200, -12);
    assert.deepEqual(env, [
      [50, -3],
      [100, 0],
      [200, -12],
    ]);

    env = addPoint(env, 75, -1.5);
    assert.deepEqual(env, [
      [50, -3],
      [75, -1.5],
      [100, 0],
      [200, -12],
    ]);
  });

  test("replaces db when frame already exists", () => {
    const original = [
      [50, -3],
      [100, 0],
    ];
    const env = addPoint(original, 50, -10);
    assert.deepEqual(env, [
      [50, -10],
      [100, 0],
    ]);
  });

  test("does not mutate original envelope", () => {
    const original = Object.freeze([Object.freeze([100, 0])]);
    const env = addPoint(original, 50, -6);
    assert.deepEqual(original, [[100, 0]]);
    assert.deepEqual(env, [
      [50, -6],
      [100, 0],
    ]);
  });
});

describe("movePoint", () => {
  test("moves point within neighbours", () => {
    const env = [
      [100, 0],
      [200, -6],
      [300, 0],
    ];
    const moved = movePoint(env, 1, 250, -3);
    assert.deepEqual(moved, [
      [100, 0],
      [250, -3],
      [300, 0],
    ]);
  });

  test("clamps frame between neighbours, never equal to or past them", () => {
    const env = [
      [100, 0],
      [200, -6],
      [300, 0],
    ];
    // Attempt to move past left neighbour
    const movedLeft = movePoint(env, 1, 50, -6);
    assert.deepEqual(movedLeft, [
      [100, 0],
      [101, -6],
      [300, 0],
    ]);

    // Attempt to move equal to left neighbour
    const movedEqualLeft = movePoint(env, 1, 100, -6);
    assert.deepEqual(movedEqualLeft, [
      [100, 0],
      [101, -6],
      [300, 0],
    ]);

    // Attempt to move past right neighbour
    const movedRight = movePoint(env, 1, 400, -6);
    assert.deepEqual(movedRight, [
      [100, 0],
      [299, -6],
      [300, 0],
    ]);

    // Attempt to move equal to right neighbour
    const movedEqualRight = movePoint(env, 1, 300, -6);
    assert.deepEqual(movedEqualRight, [
      [100, 0],
      [299, -6],
      [300, 0],
    ]);
  });

  test("moves boundary points without left or right neighbour", () => {
    const env = [
      [100, 0],
      [200, -6],
    ];
    // First point has no left neighbour, clamped by right neighbour
    const movedFirst = movePoint(env, 0, 50, 2);
    assert.deepEqual(movedFirst, [
      [50, 2],
      [200, -6],
    ]);

    const movedFirstClamped = movePoint(env, 0, 250, 2);
    assert.deepEqual(movedFirstClamped, [
      [199, 2],
      [200, -6],
    ]);

    // Last point has no right neighbour, clamped by left neighbour
    const movedLast = movePoint(env, 1, 300, -12);
    assert.deepEqual(movedLast, [
      [100, 0],
      [300, -12],
    ]);

    const movedLastClamped = movePoint(env, 1, 50, -12);
    assert.deepEqual(movedLastClamped, [
      [100, 0],
      [101, -12],
    ]);
  });

  test("throws Error for out-of-range index", () => {
    const env = [[100, 0]];
    assert.throws(() => movePoint(env, -1, 50, 0), /range/i);
    assert.throws(() => movePoint(env, 1, 50, 0), /range/i);
    assert.throws(() => movePoint(env, 2, 50, 0), /range/i);
  });

  test("does not mutate original envelope", () => {
    const original = Object.freeze([Object.freeze([100, 0]), Object.freeze([200, -6])]);
    const moved = movePoint(original, 1, 150, -3);
    assert.deepEqual(original, [
      [100, 0],
      [200, -6],
    ]);
    assert.deepEqual(moved, [
      [100, 0],
      [150, -3],
    ]);
  });
});

describe("removePoint", () => {
  test("removes point at given index", () => {
    const env = [
      [100, 0],
      [200, -6],
      [300, 0],
    ];
    assert.deepEqual(removePoint(env, 1), [
      [100, 0],
      [300, 0],
    ]);
    assert.deepEqual(removePoint(env, 0), [
      [200, -6],
      [300, 0],
    ]);
    assert.deepEqual(removePoint(env, 2), [
      [100, 0],
      [200, -6],
    ]);
  });

  test("throws Error for out-of-range index", () => {
    const env = [[100, 0]];
    assert.throws(() => removePoint(env, -1), /range/i);
    assert.throws(() => removePoint(env, 1), /range/i);
    assert.throws(() => removePoint([], 0), /range/i);
  });

  test("does not mutate original envelope", () => {
    const original = Object.freeze([Object.freeze([100, 0]), Object.freeze([200, -6])]);
    const result = removePoint(original, 0);
    assert.deepEqual(original, [
      [100, 0],
      [200, -6],
    ]);
    assert.deepEqual(result, [[200, -6]]);
  });
});

describe("nearestPoint", () => {
  test("finds index of nearest point within radius", () => {
    const env = [
      [100, 0],
      [200, -6],
      [300, 0],
    ];
    assert.equal(nearestPoint(env, 102, 5), 0);
    assert.equal(nearestPoint(env, 97, 5), 0);
    assert.equal(nearestPoint(env, 205, 5), 1);
    assert.equal(nearestPoint(env, 300, 0), 2);
  });

  test("breaks ties in favor of earlier index", () => {
    const env = [
      [100, 0],
      [110, -6],
    ];
    assert.equal(nearestPoint(env, 105, 5), 0);
  });

  test("returns -1 when no point within radius", () => {
    const env = [
      [100, 0],
      [200, -6],
    ];
    assert.equal(nearestPoint(env, 106, 5), -1);
    assert.equal(nearestPoint(env, 150, 10), -1);
  });

  test("handles empty or invalid inputs", () => {
    assert.equal(nearestPoint([], 100, 10), -1);
    assert.equal(nearestPoint(null, 100, 10), -1);
    assert.equal(nearestPoint([[100, 0]], 100, -1), -1);
    assert.equal(nearestPoint([[100, 0]], 100, Number.NaN), -1);
    assert.equal(nearestPoint([[100, 0]], Number.NaN, 10), -1);
  });

  test("does not mutate input envelope", () => {
    const original = Object.freeze([Object.freeze([100, 0])]);
    assert.equal(nearestPoint(original, 100, 5), 0);
  });
});
