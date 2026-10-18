import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { loopRange, previewLoop } from "../loop-range.js";

describe("loopRange", () => {
  test("marks win over the selection", () => {
    assert.deepEqual(
      loopRange({
        inPoint: 100,
        outPoint: 500,
        selection: { start: 200, end: 600 },
        clip: { start: 0, length: 1000 },
      }),
      { start: 100, end: 500, source: "marks" },
    );
  });

  test("one mark set only falls through to the selection", () => {
    assert.deepEqual(
      loopRange({
        inPoint: 100,
        outPoint: null,
        selection: { start: 200, end: 600 },
        clip: { start: 0, length: 1000 },
      }),
      { start: 200, end: 600, source: "selection" },
    );
    assert.deepEqual(
      loopRange({
        inPoint: undefined,
        outPoint: 500,
        selection: { start: 200, end: 600 },
        clip: { start: 0, length: 1000 },
      }),
      { start: 200, end: 600, source: "selection" },
    );
  });

  test("reversed marks fall through", () => {
    assert.deepEqual(
      loopRange({
        inPoint: 500,
        outPoint: 100,
        selection: { start: 200, end: 600 },
        clip: { start: 0, length: 1000 },
      }),
      { start: 200, end: 600, source: "selection" },
    );
  });

  test("equal marks fall through", () => {
    assert.deepEqual(
      loopRange({
        inPoint: 300,
        outPoint: 300,
        selection: { start: 200, end: 600 },
        clip: { start: 0, length: 1000 },
      }),
      { start: 200, end: 600, source: "selection" },
    );
  });

  test("a selection of zero width falls through to the clip", () => {
    assert.deepEqual(
      loopRange({
        inPoint: null,
        outPoint: null,
        selection: { start: 400, end: 400 },
        clip: { start: 0, length: 1000 },
      }),
      { start: 0, end: 1000, source: "clip" },
    );
  });

  test("a missing selection falls through to the clip", () => {
    assert.deepEqual(
      loopRange({
        inPoint: null,
        outPoint: null,
        selection: null,
        clip: { start: 0, length: 1000 },
      }),
      { start: 0, end: 1000, source: "clip" },
    );
  });

  test("a clip of length 0 gives null", () => {
    assert.equal(
      loopRange({
        inPoint: null,
        outPoint: null,
        selection: null,
        clip: { start: 0, length: 0 },
      }),
      null,
    );
  });

  test("no marks, selection, or clip gives null", () => {
    assert.equal(
      loopRange({
        inPoint: null,
        outPoint: null,
        selection: null,
        clip: null,
      }),
      null,
    );
  });
});

describe("previewLoop", () => {
  test("widens by seconds each side and clamps at 0 and total", () => {
    assert.deepEqual(previewLoop({ start: 100, end: 200 }, { rate: 48000, total: 1000 }), {
      start: 0,
      end: 1000,
    });
  });

  test("rate 44100 widens by 88200 frames each side", () => {
    assert.deepEqual(previewLoop({ start: 100000, end: 110000 }, { rate: 44100, total: 300000 }), {
      start: 11800,
      end: 198200,
    });
  });

  test("a custom seconds value is respected", () => {
    assert.deepEqual(
      previewLoop({ start: 1000, end: 2000 }, { rate: 1000, total: 5000, seconds: 0.5 }),
      { start: 500, end: 2500 },
    );
  });

  test("null in gives null out", () => {
    assert.equal(previewLoop(null, { rate: 48000, total: 1000 }), null);
  });
});
