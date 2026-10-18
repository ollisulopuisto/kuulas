import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  canStartRangeDrag,
  DRAG_PX,
  dragRange,
  isDrag,
  touchedClips,
  touchedResult,
  trackRowsTouched,
} from "../range-drag.js";

const trackRow = (id, top, height = 80) => ({ kind: "track", id, top, height });
const layout = {
  rows: [
    trackRow("a", 0),
    trackRow("b", 80),
    { kind: "gap", id: "gap:2", top: 160, height: 14 },
    trackRow("c", 174),
  ],
};

describe("isDrag", () => {
  test("needs at least DRAG_PX of movement in either direction", () => {
    assert.equal(DRAG_PX, 4);
    assert.equal(isDrag({ x: 10, y: 10 }, { x: 13, y: 10 }), false);
    assert.equal(isDrag({ x: 10, y: 10 }, { x: 14, y: 10 }), true);
    assert.equal(isDrag({ x: 10, y: 10 }, { x: 10, y: 6 }), true);
    assert.equal(isDrag({ x: 10, y: 10 }, { x: 13, y: 13 }), true);
  });
});

describe("dragRange", () => {
  test("a forward drag keeps its order", () => {
    assert.deepEqual(dragRange(100, 500, 10_000), { start: 100, end: 500 });
  });
  test("a reversed drag is normalised", () => {
    assert.deepEqual(dragRange(500, 100, 10_000), { start: 100, end: 500 });
  });
  test("clamps to the project", () => {
    assert.deepEqual(dragRange(-50, 20_000, 10_000), { start: 0, end: 10_000 });
  });
  test("rounds to whole frames", () => {
    assert.deepEqual(dragRange(10.4, 20.6, 100), { start: 10, end: 21 });
  });
  test("an empty range is null", () => {
    assert.equal(dragRange(300, 300, 10_000), null);
    assert.equal(dragRange(12_000, 15_000, 10_000), null);
    assert.equal(dragRange(10, 20, 0), null);
  });
});

describe("trackRowsTouched", () => {
  test("one lane when the drag stays inside it", () => {
    assert.deepEqual(trackRowsTouched(layout, 10, 70), ["a"]);
  });
  test("every lane the vertical extent touches, in either direction", () => {
    assert.deepEqual(trackRowsTouched(layout, 10, 100), ["a", "b"]);
    assert.deepEqual(trackRowsTouched(layout, 200, 10), ["a", "b", "c"]);
  });
  test("gaps and buses are not tracks", () => {
    assert.deepEqual(trackRowsTouched(layout, 165, 170), []);
  });
  test("a drag below the last lane stops at it", () => {
    assert.deepEqual(trackRowsTouched(layout, 100, 9999), ["b", "c"]);
  });
});

describe("canStartRangeDrag", () => {
  const lane = { area: "lane", row: trackRow("a", 0), clip: null, edge: null, point: null };
  test("an empty lane starts a drag; over a clip only with Shift", () => {
    assert.equal(canStartRangeDrag(lane), true);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" } }), false);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" } }, true), true);
  });
  test("Alt over a clip body starts a drag too, but not on an edge or an envelope point", () => {
    const over = { ...lane, clip: { id: "x" } };
    assert.equal(canStartRangeDrag(over, false, true), true);
    assert.equal(canStartRangeDrag({ ...over, edge: "end" }, false, true), false);
    assert.equal(canStartRangeDrag({ ...over, point: 1 }, false, true), false);
  });
  test("not on the ruler, a bus row, a trim edge or an envelope point", () => {
    assert.equal(canStartRangeDrag({ ...lane, area: "ruler", row: null }), false);
    assert.equal(canStartRangeDrag({ ...lane, row: { kind: "bus", id: "b" } }), false);
    assert.equal(canStartRangeDrag({ ...lane, row: null }), false);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" }, edge: "start" }, true), false);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" }, point: 0 }, true), false);
    assert.equal(canStartRangeDrag(null), false);
  });
});

describe("touchedClips and touchedResult (hold Alt: the clips the range touches)", () => {
  const clip = (id, start, length) => ({ id, start, length });
  const project = {
    tracks: [
      { id: "A", clips: [clip("a1", 0, 100), clip("a2", 150, 100)] },
      { id: "B", clips: [clip("b1", 90, 100)] },
      { id: "C", clips: [clip("c1", 0, 500)] },
    ],
  };
  const range = { start: 95, end: 160 };
  test("clips overlapping the range on the lanes the drag covers", () => {
    assert.deepEqual([...touchedClips(project, range, ["A", "B"])].sort(), ["a1", "a2", "b1"]);
    assert.deepEqual([...touchedClips(project, range, ["A"])].sort(), ["a1", "a2"]);
  });
  test("the result: selection, marks spanning those clips, and their tracks", () => {
    assert.deepEqual(touchedResult(project, range, ["A", "B"]), {
      selection: new Set(["a1", "a2", "b1"]),
      start: 0,
      end: 250,
      tracks: ["A", "B"],
    });
  });
  test("tracks come back in project order, only those holding a touched clip", () => {
    const result = touchedResult(project, { start: 120, end: 130 }, ["C", "B", "A"]);
    assert.deepEqual(result.tracks, ["B", "C"]);
  });
  test("no touched clip: null, so the exact range stays", () => {
    assert.equal(touchedResult(project, { start: 300, end: 400 }, ["A", "B"]), null);
    assert.equal(touchedResult(project, range, []), null);
  });
});
