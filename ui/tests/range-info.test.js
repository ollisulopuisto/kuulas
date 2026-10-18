import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { formatRangeInfo, rangeInfo } from "../range-info.js";

const project = {
  tracks: [
    {
      clips: [
        { id: "a", start: 100, length: 50 },
        { id: "b", start: 400, length: 100 },
      ],
    },
  ],
};
const none = { inPoint: null, outPoint: null, selection: new Set(), project, rate: 1000 };

describe("rangeInfo", () => {
  test("nothing set, nothing to show", () => {
    assert.equal(rangeInfo(none), null);
    assert.equal(rangeInfo({ project, rate: 1000 }), null);
  });
  test("both marks give a range", () => {
    assert.deepEqual(rangeInfo({ ...none, inPoint: 10, outPoint: 60 }), {
      source: "marks",
      start: 10,
      end: 60,
      length: 50,
    });
  });
  test("one mark shows only that mark", () => {
    assert.deepEqual(rangeInfo({ ...none, inPoint: 10 }), {
      source: "marks",
      start: 10,
      end: null,
      length: null,
    });
    assert.deepEqual(rangeInfo({ ...none, outPoint: 70 }), {
      source: "marks",
      start: null,
      end: 70,
      length: null,
    });
  });
  test("a selection spans its clips", () => {
    assert.deepEqual(rangeInfo({ ...none, selection: new Set(["a", "b"]) }), {
      source: "selection",
      start: 100,
      end: 500,
      length: 400,
    });
  });
  test("complete marks win over a selection", () => {
    const info = rangeInfo({ ...none, inPoint: 0, outPoint: 20, selection: new Set(["a"]) });
    assert.equal(info.source, "marks");
  });
  test("a lone mark does not hide a selection; reversed marks fall back to it", () => {
    assert.equal(rangeInfo({ ...none, inPoint: 5, selection: new Set(["a"]) }).source, "selection");
    const rev = rangeInfo({ ...none, inPoint: 90, outPoint: 20, selection: new Set(["a"]) });
    assert.equal(rev.source, "selection");
  });
  test("reversed marks without a selection give no length", () => {
    const info = rangeInfo({ ...none, inPoint: 90, outPoint: 20 });
    assert.equal(info.length, null);
  });
  test("a selection of unknown clips is nothing", () => {
    assert.equal(rangeInfo({ ...none, selection: new Set(["zzz"]) }), null);
  });
});

describe("formatRangeInfo", () => {
  const format = (frame, rate) => `T${frame / rate}`;
  test("formats each side, null stays null", () => {
    assert.deepEqual(formatRangeInfo({ start: 1000, end: 3000, length: 2000 }, 1000, format), {
      inText: "T1",
      outText: "T3",
      lengthText: "T2",
    });
    assert.deepEqual(formatRangeInfo({ start: 1000, end: null, length: null }, 1000, format), {
      inText: "T1",
      outText: null,
      lengthText: null,
    });
  });
});
