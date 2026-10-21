// A clip group (Clip.group, Edit > Group) reads as one object: one outer outline round all
// its members (owner, 2026-10-21). Pure geometry: group-outline.js groupOutlines.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { GROUP_OUTSET, groupOutlines } from "../group-outline.js";

const rows = [
  { kind: "track", id: "t1", top: 0, height: 80 },
  { kind: "track", id: "t2", top: 80, height: 80 },
  { kind: "track", id: "t3", top: 160, height: 80 },
];
const clip = (id, start, length, group) => ({ id, start, length, offset: 0, group });
const project = {
  tracks: [
    { id: "t1", clips: [clip("a", 1000, 1000, "g1"), clip("b", 3000, 500, null)] },
    { id: "t2", clips: [clip("c", 1500, 1000, "g1")] },
    { id: "t3", clips: [clip("d", 5000, 500, "g2"), clip("e", 6000, 500, "g2")] },
  ],
};
const view = { scroll: 0, zoom: 10, scrollY: 0, rulerHeight: 24 };

describe("groupOutlines", () => {
  test("one box per group round every member's body, outset by GROUP_OUTSET", () => {
    const boxes = groupOutlines(project, rows, view);
    assert.equal(boxes.length, 2);
    const g1 = boxes.find((box) => box.group === "g1");
    // a: x 100..200, lane t1 body y 24+2 .. 24+78; c: x 150..250, lane t2 body to 24+158.
    assert.deepEqual(
      { x: g1.x, y: g1.y, w: g1.w, h: g1.h },
      {
        x: 100 - GROUP_OUTSET,
        y: 26 - GROUP_OUTSET,
        w: 150 + 2 * GROUP_OUTSET,
        h: 156 + 2 * GROUP_OUTSET,
      },
    );
  });

  test("a group within one track spans its members only", () => {
    const g2 = groupOutlines(project, rows, view).find((box) => box.group === "g2");
    assert.equal(g2.x, 500 - GROUP_OUTSET);
    assert.equal(g2.w, 150 + 2 * GROUP_OUTSET);
  });

  test("ungrouped clips, and a group of one, get none", () => {
    const lone = { tracks: [{ id: "t1", clips: [clip("a", 0, 100, "g9"), clip("b", 200, 100)] }] };
    assert.deepEqual(groupOutlines(lone, rows, view), []);
  });

  test("members on a hidden (collapsed) track do not stretch the box", () => {
    const boxes = groupOutlines(project, rows.slice(0, 1), view);
    assert.deepEqual(boxes, [], "only one member of g1 is laid out: no box");
  });
});
