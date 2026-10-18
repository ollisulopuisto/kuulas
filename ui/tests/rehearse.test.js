import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { playSelectionRequest, rehearseRequest } from "../rehearse.js";

const S = 48000;

describe("rehearse the edit (Hindenburg's Ctrl+Shift+Space)", () => {
  test("starts 3 s before the in point, jumps over the range, plays on to the end", () => {
    assert.deepEqual(rehearseRequest({ inPoint: 10 * S, outPoint: 20 * S }, S), {
      at: 7 * S,
      until: null,
      skip: [[10 * S, 20 * S]],
    });
  });
  test("never starts before the beginning; the pre-roll can be given", () => {
    assert.equal(rehearseRequest({ inPoint: S, outPoint: 5 * S }, S).at, 0);
    assert.equal(rehearseRequest({ inPoint: 10 * S, outPoint: 20 * S }, S, 5).at, 5 * S);
  });
  test("needs both marks, in before out", () => {
    assert.equal(rehearseRequest({ inPoint: 100 }, S), null);
    assert.equal(rehearseRequest({ outPoint: 100 }, S), null);
    assert.equal(rehearseRequest({ inPoint: 500, outPoint: 100 }, S), null);
    assert.equal(rehearseRequest({ inPoint: 100, outPoint: 100 }, S), null);
  });
});

describe("play selection (Shift+Space)", () => {
  test("plays from the in point to the out point and stops", () => {
    assert.deepEqual(playSelectionRequest({ inPoint: 1000, outPoint: 5000 }), {
      at: 1000,
      until: 5000,
      skip: null,
    });
  });
  test("needs a range", () => {
    assert.equal(playSelectionRequest({ inPoint: 1000 }), null);
    assert.equal(playSelectionRequest({}), null);
  });
});
