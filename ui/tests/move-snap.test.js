import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { advanceDelta, movedSpans, moveTargets, snapMove } from "../move-snap.js";

describe("fine adjust: holding the modifier moves a tenth as far", () => {
  test("normal: the delta follows the pointer in frames", () => {
    let d = advanceDelta({ delta: 0, lastX: 100 }, 110, { fine: false, zoom: 50 });
    assert.deepEqual(d, { delta: 500, lastX: 110 });
    d = advanceDelta(d, 90, { fine: false, zoom: 50 });
    assert.deepEqual(d, { delta: -500, lastX: 90 });
  });
  test("fine: a tenth, and switching mid-drag keeps what was already moved", () => {
    let d = advanceDelta({ delta: 0, lastX: 0 }, 100, { fine: false, zoom: 10 });
    assert.equal(d.delta, 1000);
    d = advanceDelta(d, 200, { fine: true, zoom: 10 });
    assert.equal(d.delta, 1100); // 100 px at a tenth: 100 frames more
  });
});

describe("snapping a moved clip's edges", () => {
  const moved = [{ start: 1000, end: 2000 }];
  test("its start snaps to a nearby edge within the radius (8 px)", () => {
    const r = snapMove({ moved, delta: 1005, targets: [2000, 9000], zoom: 1 });
    assert.equal(r.delta, 1000); // start 1000+1005 = 2005 -> 2000
    assert.equal(r.at, 2000);
  });
  test("its end snaps too, whichever edge is closer", () => {
    const r = snapMove({ moved, delta: 3996, targets: [7000, 5000], zoom: 1 });
    assert.equal(r.delta, 4000); // end 2000+3996 = 5996? no: start 4996 -> 5000
    assert.equal(r.at, 5000);
  });
  test("the radius is in pixels: zoomed out, a bigger frame distance still snaps", () => {
    const r = snapMove({ moved, delta: 1050, targets: [2000], zoom: 10 });
    assert.equal(r.delta, 1000); // 50 frames = 5 px at 10 frames per pixel
    assert.equal(snapMove({ moved, delta: 1050, targets: [2000], zoom: 1 }).at, null);
  });
  test("nothing near, no snap: the delta is returned as it was", () => {
    assert.deepEqual(snapMove({ moved, delta: 123, targets: [90000], zoom: 1 }), {
      delta: 123,
      at: null,
    });
    assert.deepEqual(snapMove({ moved, delta: 123, targets: [], zoom: 1 }), {
      delta: 123,
      at: null,
    });
  });
  test("a selection snaps as a block: the earliest start and the latest end count", () => {
    const block = [
      { start: 1000, end: 2000 },
      { start: 5000, end: 6000 },
    ];
    const r = snapMove({ moved: block, delta: 2003, targets: [3000, 7000], zoom: 1 });
    assert.equal(r.delta, 2000);
  });
});

describe("what to snap to", () => {
  const project = {
    tracks: [
      {
        id: "a",
        clips: [
          { id: "a1", start: 0, length: 100 },
          { id: "a2", start: 300, length: 50 },
        ],
      },
      { id: "b", clips: [{ id: "b1", start: 120, length: 30 }] },
    ],
  };
  test("every other clip's edges, the playhead and the marks; the moved clips are left out", () => {
    const t = moveTargets(project, ["a2"], { playhead: 77, inPoint: 200, outPoint: 260 });
    assert.deepEqual(t, [0, 77, 100, 120, 150, 200, 260]);
  });
  test("missing marks are skipped and duplicates merged", () => {
    const t = moveTargets(project, [], { playhead: 100, inPoint: null, outPoint: undefined });
    assert.deepEqual(t, [0, 100, 120, 150, 300, 350]);
  });
});

describe("the moved clips' spans", () => {
  test("start and end of the clips with the given ids", () => {
    const project = { tracks: [{ id: "a", clips: [{ id: "x", start: 10, length: 5 }] }] };
    assert.deepEqual(movedSpans(project, ["x", "gone"]), [{ start: 10, end: 15 }]);
  });
});
