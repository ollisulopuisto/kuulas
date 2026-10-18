import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { markDrawing, setInPoint, setOutPoint } from "../marks.js";

describe("setting the in and out marks", () => {
  test("a lone mark is set as it is", () => {
    assert.deepEqual(setOutPoint({ inPoint: null, outPoint: null }, 500), {
      inPoint: null,
      outPoint: 500,
    });
    assert.deepEqual(setInPoint({ inPoint: null, outPoint: null }, 500), {
      inPoint: 500,
      outPoint: null,
    });
  });
  test("an out mark before the in mark replaces the in mark", () => {
    assert.deepEqual(setOutPoint({ inPoint: 800, outPoint: null }, 300), {
      inPoint: null,
      outPoint: 300,
    });
  });
  test("an in mark after the out mark replaces the out mark", () => {
    assert.deepEqual(setInPoint({ inPoint: null, outPoint: 300 }, 800), {
      inPoint: 800,
      outPoint: null,
    });
  });
  test("a mark that keeps the order leaves the other one alone", () => {
    assert.deepEqual(setOutPoint({ inPoint: 100, outPoint: null }, 300), {
      inPoint: 100,
      outPoint: 300,
    });
    assert.deepEqual(setInPoint({ inPoint: null, outPoint: 300 }, 100), {
      inPoint: 100,
      outPoint: 300,
    });
  });
  test("moving a mark onto the other makes no range, so the other goes", () => {
    assert.deepEqual(setOutPoint({ inPoint: 300, outPoint: null }, 300), {
      inPoint: null,
      outPoint: 300,
    });
  });
});

describe("what to draw for the marks", () => {
  test("nothing for no marks", () => {
    assert.deepEqual(markDrawing({ inPoint: null, outPoint: null }), {
      inFrame: null,
      outFrame: null,
      range: null,
    });
  });
  test("a lone out mark is drawn, with no range tint", () => {
    assert.deepEqual(markDrawing({ inPoint: null, outPoint: 500 }), {
      inFrame: null,
      outFrame: 500,
      range: null,
    });
  });
  test("both marks give the range tint", () => {
    assert.deepEqual(markDrawing({ inPoint: 100, outPoint: 500 }), {
      inFrame: 100,
      outFrame: 500,
      range: { start: 100, end: 500 },
    });
  });
  test("reversed marks (an old saved state) draw no range tint", () => {
    assert.equal(markDrawing({ inPoint: 500, outPoint: 100 }).range, null);
  });
});
