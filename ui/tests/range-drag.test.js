import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { canStartRangeDrag, DRAG_PX, dragRange, isDrag, trackRowsTouched } from "../range-drag.js";

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
  test("empty lane and waveform start a drag", () => {
    assert.equal(canStartRangeDrag(lane), true);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" } }), true);
  });
  test("not on the ruler, a bus row, a trim edge or an envelope point", () => {
    assert.equal(canStartRangeDrag({ ...lane, area: "ruler", row: null }), false);
    assert.equal(canStartRangeDrag({ ...lane, row: { kind: "bus", id: "b" } }), false);
    assert.equal(canStartRangeDrag({ ...lane, row: null }), false);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" }, edge: "start" }), false);
    assert.equal(canStartRangeDrag({ ...lane, clip: { id: "x" }, point: 0 }), false);
    assert.equal(canStartRangeDrag(null), false);
  });
});
