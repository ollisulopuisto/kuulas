import assert from "node:assert/strict";
import test from "node:test";
import { guides, snapDelta, snapTarget } from "../guide-lines.js";

test("guides: closest other edge within show threshold", () => {
  const movedEdges = [1000];
  const otherEdges = [
    { track: "t1", frame: 1050 }, // diff = 50 frames -> at zoom 2: 25 px <= show (40)
    { track: "t2", frame: 1200 }, // diff = 200 frames -> 100 px > show
  ];
  const res = guides(movedEdges, otherEdges, 2);
  assert.equal(res.length, 1);
  assert.deepEqual(res[0], {
    frame: 1000,
    edgeFrame: 1050,
    track: "t1",
    px: 25,
    strength: (40 - 25) / 40, // 15 / 40 = 0.375
    snap: false, // 25 > 8
  });
});

test("guides: distance > show returns empty array", () => {
  const movedEdges = [1000];
  const otherEdges = [
    { track: "t1", frame: 1100 }, // diff 100 frames at zoom 2 is 50 px > 40
  ];
  assert.deepEqual(guides(movedEdges, otherEdges, 2), []);
});

test("guides: exact match at distance 0 gives strength 1 and snap true", () => {
  const movedEdges = [1000];
  const otherEdges = [{ track: "t1", frame: 1000 }];
  const res = guides(movedEdges, otherEdges, 5);
  assert.equal(res.length, 1);
  assert.deepEqual(res[0], {
    frame: 1000,
    edgeFrame: 1000,
    track: "t1",
    px: 0,
    strength: 1,
    snap: true,
  });
});

test("guides: snap threshold boundary (px <= snap)", () => {
  const zoom = 10;
  // snap = 8 px -> 80 frames
  // moved 1000, other 1080 -> diff 80 frames -> 8 px -> snap true
  const res1 = guides([1000], [{ track: "t1", frame: 1080 }], zoom, {
    show: 40,
    snap: 8,
  });
  assert.equal(res1[0].px, 8);
  assert.equal(res1[0].snap, true);

  // moved 1000, other 1081 -> diff 81 frames -> 8.1 px -> snap false
  const res2 = guides([1000], [{ track: "t1", frame: 1081 }], zoom, {
    show: 40,
    snap: 8,
  });
  assert.equal(res2[0].px, 8.1);
  assert.equal(res2[0].snap, false);
});

test("guides: strength is linear from 1 at 0 to 0 at show", () => {
  const zoom = 1;
  // at show / 2 (20 px) -> strength should be 0.5
  const res = guides([100], [{ track: "t1", frame: 120 }], zoom, { show: 40 });
  assert.equal(res[0].strength, 0.5);

  // at distance show (40 px) -> strength should be 0
  const resAtShow = guides([100], [{ track: "t1", frame: 140 }], zoom, {
    show: 40,
  });
  assert.equal(resAtShow[0].strength, 0);
});

test("guides: sorted by px ascending", () => {
  const movedEdges = [100, 500];
  const otherEdges = [
    { track: "t1", frame: 120 }, // diff 20 from 100 -> 20 px
    { track: "t2", frame: 505 }, // diff 5 from 500 -> 5 px
  ];
  const res = guides(movedEdges, otherEdges, 1);
  assert.equal(res.length, 2);
  assert.equal(res[0].frame, 500);
  assert.equal(res[0].px, 5);
  assert.equal(res[1].frame, 100);
  assert.equal(res[1].px, 20);
});

test("guides: at most one entry per other edge (closest moved edge wins)", () => {
  // moved edges at 100 and 105
  // single other edge at 102:
  // distance from 105 is 3 frames (3 px); distance from 100 is 2 frames (2 px)
  const movedEdges = [100, 105];
  const otherEdges = [{ track: "t1", frame: 102 }];
  const res = guides(movedEdges, otherEdges, 1);
  assert.equal(res.length, 1);
  assert.equal(res[0].frame, 100);
  assert.equal(res[0].edgeFrame, 102);
  assert.equal(res[0].px, 2);
});

test("guides: capped at at most 4 entries", () => {
  const movedEdges = [100, 200, 300, 400, 500, 600];
  const otherEdges = [
    { track: "t1", frame: 101 }, // 1 px
    { track: "t2", frame: 202 }, // 2 px
    { track: "t3", frame: 303 }, // 3 px
    { track: "t4", frame: 404 }, // 4 px
    { track: "t5", frame: 505 }, // 5 px
    { track: "t6", frame: 606 }, // 6 px
  ];
  const res = guides(movedEdges, otherEdges, 1);
  assert.equal(res.length, 4);
  assert.deepEqual(
    res.map((g) => g.px),
    [1, 2, 3, 4],
  );
});

test("guides: invalid inputs and non-finite edges are skipped", () => {
  assert.deepEqual(guides([100], [{ track: "t1", frame: 100 }], 0), []);
  assert.deepEqual(guides([100], [{ track: "t1", frame: 100 }], -1), []);
  assert.deepEqual(guides([100], [{ track: "t1", frame: 100 }], Number.NaN), []);
  assert.deepEqual(guides([], [{ track: "t1", frame: 100 }], 1), []);
  assert.deepEqual(guides([100], [], 1), []);
  assert.deepEqual(guides(null, null, 1), []);

  // Non-finite edges in list
  const res = guides(
    [Number.NaN, 100, Number.POSITIVE_INFINITY],
    [null, { track: "t1", frame: Number.NaN }, { track: "t2", frame: 102 }],
    1,
  );
  assert.equal(res.length, 1);
  assert.equal(res[0].frame, 100);
  assert.equal(res[0].edgeFrame, 102);
});

test("snapTarget: edgeFrame of the first entry with snap true, or null", () => {
  const list = [
    { frame: 100, edgeFrame: 102, snap: true },
    { frame: 200, edgeFrame: 201, snap: true },
  ];
  assert.equal(snapTarget(list), 102);

  const noSnap = [
    { frame: 100, edgeFrame: 120, snap: false },
    { frame: 200, edgeFrame: 230, snap: false },
  ];
  assert.equal(snapTarget(noSnap), null);
  assert.equal(snapTarget([]), null);
  assert.equal(snapTarget(null), null);
});

test("snapDelta: frames moved clip should shift to land on edge (edgeFrame - frame), or 0", () => {
  // Edge is to the right (+2)
  const list1 = [{ frame: 100, edgeFrame: 102, snap: true }];
  assert.equal(snapDelta(list1), 2);

  // Edge is to the left (-3)
  const list2 = [{ frame: 100, edgeFrame: 97, snap: true }];
  assert.equal(snapDelta(list2), -3);

  // First snapped entry wins
  const listMultiple = [
    { frame: 100, edgeFrame: 120, snap: false },
    { frame: 200, edgeFrame: 195, snap: true },
  ];
  assert.equal(snapDelta(listMultiple), -5);

  // No snap
  assert.equal(snapDelta([{ frame: 100, edgeFrame: 120, snap: false }]), 0);
  assert.equal(snapDelta([]), 0);
  assert.equal(snapDelta(null), 0);
});

test("immutability: input arrays and objects are never mutated", () => {
  const moved = Object.freeze([Object.freeze(100), Object.freeze(200)]);
  const other = Object.freeze([
    Object.freeze({ track: "t1", frame: 105 }),
    Object.freeze({ track: "t2", frame: 202 }),
  ]);
  const res = guides(moved, other, 1);
  assert.equal(res.length, 2);
  assert.equal(snapTarget(res), 202);
  assert.equal(snapDelta(res), 2);
});
