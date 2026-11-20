import assert from "node:assert/strict";
import { test } from "node:test";
import {
  EDGE_PX,
  gripPill,
  hoverTrimEdge,
  PILL_HEIGHT,
  PILL_WIDTH,
  sameHandle,
} from "../drag-handle.js";

test("grip pill centres on the point and carries three centred bars", () => {
  const pill = gripPill(100, 40);
  assert.equal(pill.x, 100 - PILL_WIDTH / 2);
  assert.equal(pill.y, 40 - PILL_HEIGHT / 2);
  assert.equal(pill.width, PILL_WIDTH);
  assert.equal(pill.height, PILL_HEIGHT);
  assert.equal(pill.radius, PILL_HEIGHT / 2);
  assert.equal(pill.bars.length, 3);
  const centres = pill.bars.map((x) => x + pill.barWidth / 2);
  assert.deepEqual(centres, [94, 100, 106]);
  assert.equal(pill.barY + pill.barHeight / 2, 40);
});

test("hoverTrimEdge: only a clip edge on a track row, and never during a session", () => {
  const hit = { clip: { id: "c1" }, edge: "end", row: { kind: "track" } };
  assert.deepEqual(hoverTrimEdge(hit, false), { clipId: "c1", edge: "end" });
  assert.equal(hoverTrimEdge(hit, true), null);
  assert.equal(hoverTrimEdge({ ...hit, edge: null }, false), null);
  assert.equal(hoverTrimEdge({ ...hit, clip: null }, false), null);
  assert.equal(hoverTrimEdge({ ...hit, row: { kind: "bus" } }, false), null);
  assert.equal(hoverTrimEdge({ ...hit, row: null }, false), null);
  assert.equal(hoverTrimEdge(null, false), null);
});

test("sameHandle: a move within one edge is no change", () => {
  assert.equal(sameHandle(null, null), true);
  assert.equal(sameHandle({ clipId: "c", edge: "start" }, { clipId: "c", edge: "start" }), true);
  assert.equal(sameHandle({ clipId: "c", edge: "start" }, { clipId: "c", edge: "end" }), false);
  assert.equal(sameHandle({ clipId: "a", edge: "end" }, { clipId: "b", edge: "end" }), false);
  assert.equal(sameHandle(null, { clipId: "c", edge: "end" }), false);
  assert.equal(sameHandle({ clipId: "c", edge: "end" }, null), false);
});

test("the hovered edge line is visibly thicker than the resting 1 px clip border", () => {
  assert.ok(EDGE_PX >= 3);
});
