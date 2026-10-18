import assert from "node:assert/strict";
import test, { describe } from "node:test";
import { snap, snapToGrid, snapToPoints } from "../snap.js";

describe("snapToPoints", () => {
  test("finds nearest point within radius", () => {
    const points = [100, 200, 300];
    assert.equal(snapToPoints(104, points, 5), 100);
    assert.equal(snapToPoints(96, points, 5), 100);
    assert.equal(snapToPoints(200, points, 5), 200);
  });

  test("breaks ties in favor of smaller point", () => {
    const points = [100, 110];
    assert.equal(snapToPoints(105, points, 5), 100);
    const pointsRev = [110, 100];
    assert.equal(snapToPoints(105, pointsRev, 5), 100);
  });

  test("returns null when no point is within radius", () => {
    const points = [100, 200];
    assert.equal(snapToPoints(106, points, 5), null);
    assert.equal(snapToPoints(50, points, 10), null);
  });

  test("inclusive boundary check for radius", () => {
    const points = [100];
    assert.equal(snapToPoints(105, points, 5), 100);
    assert.equal(snapToPoints(95, points, 5), 100);
    assert.equal(snapToPoints(106, points, 5), null);
  });

  test("handles empty, missing, or invalid points and radius", () => {
    assert.equal(snapToPoints(100, [], 10), null);
    assert.equal(snapToPoints(100, null, 10), null);
    assert.equal(snapToPoints(100, undefined, 10), null);
    assert.equal(snapToPoints(100, [100], -1), null);
    assert.equal(snapToPoints(100, [100], Number.NaN), null);
    assert.equal(snapToPoints(100, [100], Infinity), null);
    assert.equal(snapToPoints(Number.NaN, [100], 10), null);
  });

  test("does not mutate points array", () => {
    const points = Object.freeze([300, 100, 200]);
    assert.equal(snapToPoints(102, points, 10), 100);
  });
});

describe("snapToGrid", () => {
  test("snaps to multiples of step", () => {
    assert.equal(snapToGrid(12, 10), 10);
    assert.equal(snapToGrid(17, 10), 20);
    assert.equal(snapToGrid(20, 10), 20);
    assert.equal(snapToGrid(0, 10), 0);
  });

  test("halves round up", () => {
    assert.equal(snapToGrid(15, 10), 20);
    assert.equal(snapToGrid(25, 10), 30);
    assert.equal(snapToGrid(-15, 10), -10);
  });

  test("returns frame unchanged when step is not a finite positive number", () => {
    assert.equal(snapToGrid(12, 0), 12);
    assert.equal(snapToGrid(12, -10), 12);
    assert.equal(snapToGrid(12, null), 12);
    assert.equal(snapToGrid(12, undefined), 12);
    assert.equal(snapToGrid(12, Number.NaN), 12);
    assert.equal(snapToGrid(12, Infinity), 12);
  });

  test("handles fractional and step of 1", () => {
    assert.equal(snapToGrid(12.3, 1), 12);
    assert.equal(snapToGrid(12.7, 1), 13);
  });
});

describe("snap", () => {
  test("points win over the grid", () => {
    const points = [102];
    assert.equal(snap(101, { points, radius: 5, step: 10 }), 102);
  });

  test("grid applies when points do not match or are out of range", () => {
    const points = [100];
    assert.equal(snap(123, { points, radius: 5, step: 10 }), 120);
    assert.equal(snap(123, { step: 10 }), 120);
  });

  test("returns frame unchanged when neither points nor grid applies", () => {
    assert.equal(snap(123, {}), 123);
    assert.equal(snap(123, null), 123);
    assert.equal(snap(123, { points: [10], radius: 2, step: 0 }), 123);
  });

  test("does not mutate inputs", () => {
    const points = Object.freeze([50, 100]);
    const opts = Object.freeze({ points, radius: 5, step: 10 });
    assert.equal(snap(98, opts), 100);
  });
});
