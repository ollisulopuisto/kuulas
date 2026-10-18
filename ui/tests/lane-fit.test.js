import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { fitLaneHeights } from "../lane-fit.js";

describe("fitLaneHeights", () => {
  test("no tracks: heights empty, total 0, no overflow", () => {
    assert.deepEqual(fitLaneHeights({ available: 500, tracks: [] }), {
      heights: {},
      total: 0,
      overflow: false,
    });
  });

  test("available of 0: empty tracks gives total 0, no overflow", () => {
    assert.deepEqual(fitLaneHeights({ available: 0, tracks: [] }), {
      heights: {},
      total: 0,
      overflow: false,
    });
  });

  test("available of 0: visible tracks clamped to min, overflow true", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 0,
        tracks: [{ id: "t1" }, { id: "t2" }],
        min: 28,
      }),
      {
        heights: { t1: 28, t2: 28 },
        total: 56,
        overflow: true,
      },
    );
  });

  test("available of 0: collapsed tracks take collapsedHeight, overflow true", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 0,
        tracks: [{ id: "t1", collapsed: true }],
        collapsedHeight: 8,
      }),
      {
        heights: { t1: 8 },
        total: 8,
        overflow: true,
      },
    );
  });

  test("equal split: visible tracks share available space equally", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 300,
        tracks: [{ id: "t1" }, { id: "t2" }, { id: "t3" }],
      }),
      {
        heights: { t1: 100, t2: 100, t3: 100 },
        total: 300,
        overflow: false,
      },
    );
  });

  test("clamp to max with redistribution: tracks that hit max leave remainder to others", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 250,
        tracks: [{ id: "t1", max: 100 }, { id: "t2" }],
        min: 28,
        max: 160,
      }),
      {
        heights: { t1: 100, t2: 150 },
        total: 250,
        overflow: false,
      },
    );
  });

  test("clamp to max with redistribution: cascading max clamps repeat until stable", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 300,
        tracks: [{ id: "t1", max: 80 }, { id: "t2", max: 100 }, { id: "t3" }],
        min: 28,
        max: 160,
      }),
      {
        heights: { t1: 80, t2: 100, t3: 120 },
        total: 300,
        overflow: false,
      },
    );
  });

  test("everyone hit max: nothing more added, total does not exceed available", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 500,
        tracks: [{ id: "t1" }, { id: "t2" }],
        min: 28,
        max: 160,
      }),
      {
        heights: { t1: 160, t2: 160 },
        total: 320,
        overflow: false,
      },
    );
  });

  test("clamp to min with overflow: insufficient space gives min to all visible tracks", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 50,
        tracks: [{ id: "t1" }, { id: "t2" }],
        min: 28,
      }),
      {
        heights: { t1: 28, t2: 28 },
        total: 56,
        overflow: true,
      },
    );
  });

  test("collapsed strips: collapsed tracks take collapsedHeight", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 200,
        tracks: [{ id: "t1", collapsed: true }, { id: "t2" }, { id: "t3", collapsed: true }],
        collapsedHeight: 8,
        max: 160,
      }),
      {
        heights: { t1: 8, t2: 160, t3: 8 },
        total: 176,
        overflow: false,
      },
    );

    assert.deepEqual(
      fitLaneHeights({
        available: 108,
        tracks: [{ id: "t1", collapsed: true }, { id: "t2" }, { id: "t3" }],
        collapsedHeight: 8,
      }),
      {
        heights: { t1: 8, t2: 50, t3: 50 },
        total: 108,
        overflow: false,
      },
    );
  });

  test("one focused track taking rounding leftovers", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 100,
        tracks: [{ id: "t1" }, { id: "t2", focused: true }, { id: "t3" }],
      }),
      {
        heights: { t1: 33, t2: 34, t3: 33 },
        total: 100,
        overflow: false,
      },
    );

    assert.deepEqual(
      fitLaneHeights({
        available: 101,
        tracks: [{ id: "t1" }, { id: "t2", focused: true }, { id: "t3" }],
      }),
      {
        heights: { t1: 33, t2: 35, t3: 33 },
        total: 101,
        overflow: false,
      },
    );
  });

  test("focused track takes leftovers only up to max", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 321,
        tracks: [
          { id: "t1", max: 160 },
          { id: "t2", focused: true, max: 160 },
        ],
        max: 160,
      }),
      {
        heights: { t1: 160, t2: 160 },
        total: 320,
        overflow: false,
      },
    );
  });

  test("no focused track leaves rounding leftovers out", () => {
    assert.deepEqual(
      fitLaneHeights({
        available: 100,
        tracks: [{ id: "t1" }, { id: "t2" }, { id: "t3" }],
      }),
      {
        heights: { t1: 33, t2: 33, t3: 33 },
        total: 99,
        overflow: false,
      },
    );
  });
});
