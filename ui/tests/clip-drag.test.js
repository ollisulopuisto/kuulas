import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  canStartClipDrag,
  clipDragChange,
  clipDragIds,
  inMoveZone,
  MOVE_STRIP_PX,
  moveBoxes,
  moveGhosts,
  resolveMove,
  targetTrackRow,
} from "../clip-drag.js";
import { RULER_HEIGHT } from "../lanes.js";

const S = 48_000;
const project = {
  rate: S,
  tracks: [
    { id: "A", clips: [{ id: "a", start: 2 * S, length: 4 * S }] },
    { id: "B", clips: [{ id: "b", start: 5 * S, length: 2 * S }] },
    { id: "C", clips: [{ id: "c", start: S, length: S }] },
  ],
};
const trackRow = (id, index, top) => ({ kind: "track", id, index, top, height: 80 });
const layout = {
  rows: [
    trackRow("A", 0, 0),
    trackRow("B", 1, 80),
    { kind: "gap", id: "gap:2", top: 160, height: 14 },
    trackRow("C", 2, 174),
  ],
};

describe("the grab zone", () => {
  test("is the label strip along the clip's top", () => {
    assert.equal(inMoveZone(2), true);
    assert.equal(inMoveZone(MOVE_STRIP_PX - 1), true);
    assert.equal(inMoveZone(MOVE_STRIP_PX + 5), false);
    assert.equal(inMoveZone(-1), false);
  });

  test("starts on a clip body only: not an edge, an envelope point or a bus row", () => {
    const clip = { id: "a" };
    const row = { kind: "track" };
    assert.equal(canStartClipDrag({ clip, edge: null, point: null, row }, 5), true);
    assert.equal(canStartClipDrag({ clip, edge: "end", point: null, row }, 5), false);
    assert.equal(canStartClipDrag({ clip, edge: null, point: 0, row }, 5), false);
    assert.equal(canStartClipDrag({ clip, edge: null, point: null, row }, 60), false);
    assert.equal(canStartClipDrag({ clip: null, edge: null, point: null, row }, 5), false);
    assert.equal(
      canStartClipDrag({ clip, edge: null, point: null, row: { kind: "bus" } }, 5),
      false,
    );
  });
});

describe("clipDragIds", () => {
  test("the selection when it holds the pressed clip, else the clip alone", () => {
    assert.deepEqual(clipDragIds("a", new Set(["a", "b"])), ["a", "b"]);
    assert.deepEqual(clipDragIds("c", new Set(["a", "b"])), ["c"]);
    assert.deepEqual(clipDragIds("a", new Set()), ["a"]);
  });
});

describe("targetTrackRow", () => {
  test("the track row under the pointer", () => {
    assert.equal(targetTrackRow(layout, 100).id, "B");
  });
  test("a gap row between: the nearer track; outside: the first or last", () => {
    assert.equal(targetTrackRow(layout, 170).id, "C");
    assert.equal(targetTrackRow(layout, -30).id, "A");
    assert.equal(targetTrackRow(layout, 900).id, "C");
  });
  test("null without track rows", () => {
    assert.equal(targetTrackRow({ rows: [] }, 5), null);
  });
});

describe("resolveMove", () => {
  test("time by the pointer's travel, track by index difference", () => {
    const r = resolveMove(project, ["a"], { deltaFrames: S, fromIndex: 0, toIndex: 1 });
    assert.deepEqual(r, { delta: S, direction: 1 });
  });
  test("the earliest clip stops at frame 0", () => {
    const r = resolveMove(project, ["a", "c"], { deltaFrames: -3 * S, fromIndex: 0, toIndex: 0 });
    assert.equal(r.delta, -S);
  });
  test("the selection keeps its shape at the first and last track", () => {
    const down = { deltaFrames: 0, fromIndex: 1, toIndex: 2 };
    assert.equal(resolveMove(project, ["a", "b"], down).direction, 1);
    assert.equal(resolveMove(project, ["b", "c"], down).direction, 0);
    const up = { deltaFrames: 0, fromIndex: 1, toIndex: 0 };
    assert.equal(resolveMove(project, ["a", "b"], up).direction, 0);
  });
  test("whole frames", () => {
    const r = resolveMove(project, ["a"], { deltaFrames: 10.6, fromIndex: 0, toIndex: 0 });
    assert.equal(r.delta, 11);
  });
});

describe("moveGhosts and moveBoxes", () => {
  test("each clip at its new place on its new track", () => {
    const ghosts = moveGhosts(project, ["a", "b"], { delta: S, direction: 1 });
    assert.deepEqual(ghosts, [
      { clipId: "a", trackId: "B", start: 3 * S, end: 7 * S },
      { clipId: "b", trackId: "C", start: 6 * S, end: 8 * S },
    ]);
  });
  test("pixel boxes sit in the target lane", () => {
    const ghosts = moveGhosts(project, ["a"], { delta: 0, direction: 1 });
    const view = { scroll: 0, zoom: 100, scrollY: 0 };
    const [box] = moveBoxes(ghosts, { view, layout });
    assert.equal(box.x, (2 * S) / 100);
    assert.equal(box.w, (4 * S) / 100);
    assert.equal(box.y, RULER_HEIGHT + 80 + 2);
    assert.equal(box.h, 76);
  });
});

describe("clipDragChange", () => {
  test("one move_clips_to_track edit with the group setting", () => {
    const c = clipDragChange(["a"], { delta: 5, direction: -1 }, true);
    assert.equal(c.op, "move_clips_to_track");
    assert.deepEqual(c.args, { clip_ids: ["a"], direction: -1, delta: 5, group_editing: true });
    assert.equal(c.labelKey, "ui.clipdrag.move");
  });
  test("nothing to send when nothing moved", () => {
    assert.equal(clipDragChange(["a"], { delta: 0, direction: 0 }, true), null);
  });
});
