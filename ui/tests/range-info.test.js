import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { formatRangeInfo, rangeInfo, rangeLine } from "../range-info.js";

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

describe("rangeLine (the status bar text)", () => {
  const fmt = (frame, rate) => `T${frame / rate}`;
  const tr = (key, values = {}) => `${key}${values.count ?? ""}`;
  const line = (extra) => rangeLine({ ...none, ...extra }, 1000, fmt, tr);
  const clipsText = "ui.range.clips_one · T0.1-T0.15 · T0.05";

  test("nothing set, nothing to say", () => {
    assert.equal(line({}), null);
  });
  test("marks alone say nothing: the corner shows them", () => {
    assert.equal(line({ inPoint: 1000, outPoint: 3000 }), null);
    assert.equal(line({ inPoint: 1000 }), null);
  });
  test("a selection reads as clips: count, start-end, length", () => {
    assert.equal(
      line({ selection: new Set(["a", "b"]) }),
      "ui.range.clips_many2 · T0.1-T0.5 · T0.4",
    );
    assert.equal(line({ selection: new Set(["a"]) }), clipsText);
  });
  test("marks and a different selection: the marks are not repeated", () => {
    assert.equal(line({ inPoint: 0, outPoint: 1000, selection: new Set(["a"]) }), clipsText);
  });
  test("marks that say the same as the selection leave only the count", () => {
    assert.equal(
      line({ inPoint: 100, outPoint: 150, selection: new Set(["a"]) }),
      "ui.range.clips_one",
    );
  });
  test("a lone mark does not hide the selection", () => {
    assert.equal(line({ inPoint: 5, selection: new Set(["a"]) }), clipsText);
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
