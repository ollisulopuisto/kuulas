import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  canStartClipDrag,
  clipDragChange,
  clipDragIds,
  groupBounds,
  inMoveZone,
  MOVE_STRIP_PX,
  moveBoxes,
  moveGhosts,
  portionDragEdit,
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
    // The whole clip body moves it (owner, 2026-10-18: Hindenburg's way), not only the strip.
    assert.equal(canStartClipDrag({ clip, edge: null, point: null, row }, 60), true);
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
  test("one move_clips_to_track edit; sync partners and group editing are not part of it", () => {
    const c = clipDragChange(["a"], { delta: 5, direction: -1 });
    assert.equal(c.op, "move_clips_to_track");
    assert.deepEqual(c.args, { clip_ids: ["a"], direction: -1, delta: 5 });
    assert.equal(c.labelKey, "ui.clipdrag.move");
  });
  test("nothing to send when nothing moved", () => {
    assert.equal(clipDragChange(["a"], { delta: 0, direction: 0 }), null);
  });
});

describe("group drag ghosts", () => {
  const grouped = {
    rate: S,
    tracks: [
      {
        id: "A",
        clips: [
          { id: "a1", start: S, length: S, group: "g" },
          { id: "x", start: 9 * S, length: S },
        ],
      },
      { id: "B", clips: [{ id: "b1", start: 2 * S, length: S, group: "g", muted: true }] },
      { id: "C", clips: [{ id: "c1", start: 3 * S, length: S, group: "g" }] },
    ],
  };
  const idsFor = (id) => clipDragIds(id, new Set([id]), grouped);

  test("grabbing any member drags the whole group", () => {
    assert.deepEqual([...idsFor("a1")].sort(), ["a1", "b1", "c1"]);
    assert.deepEqual([...idsFor("c1")].sort(), ["a1", "b1", "c1"]);
    assert.deepEqual(idsFor("x"), ["x"]);
  });
  test("first and last member give the same ghost set, across tracks", () => {
    const move = { delta: S / 2, direction: 0 };
    const key = (id) =>
      moveGhosts(grouped, idsFor(id), move)
        .map((g) => `${g.clipId}:${g.trackId}:${g.start}-${g.end}`)
        .sort();
    assert.deepEqual(key("a1"), key("c1"));
    assert.equal(key("a1").length, 3);
    assert.ok(key("a1").includes(`b1:B:${2.5 * S}-${3.5 * S}`));
  });
  test("a clamp at the project start keeps the offsets", () => {
    const move = resolveMove(grouped, idsFor("c1"), {
      deltaFrames: -5 * S,
      fromIndex: 2,
      toIndex: 2,
    });
    assert.equal(move.delta, -S);
    const starts = moveGhosts(grouped, idsFor("c1"), move)
      .map((g) => g.start)
      .sort();
    assert.deepEqual(starts, [0, S, 2 * S]);
  });
  test("a track change is cut back so every member stays on a track", () => {
    const move = resolveMove(grouped, idsFor("a1"), { deltaFrames: 0, fromIndex: 0, toIndex: 1 });
    assert.equal(move.direction, 0);
  });
  test("one outline round the group; none for a single clip", () => {
    assert.equal(groupBounds([{ x: 1, y: 1, w: 2, h: 2 }]), null);
    assert.deepEqual(
      groupBounds([
        { x: 10, y: 5, w: 20, h: 10 },
        { x: 0, y: 30, w: 5, h: 10 },
      ]),
      { x: 0, y: 5, w: 30, h: 35 },
    );
  });
});

describe("dragging an implicit portion", () => {
  // One clip, 0..10 s, Auto-Silence closed over 4..6 s (source frames: offset 0).
  const silenced = {
    rate: S,
    tracks: [
      {
        id: "A",
        gate: [],
        clips: [
          {
            id: "p",
            media: "m",
            start: 0,
            length: 10 * S,
            offset: 0,
            auto_silence: [[4 * S, 6 * S]],
          },
          { id: "q", media: "m", start: 12 * S, length: S, offset: 0 },
        ],
      },
    ],
  };
  const parent = silenced.tracks[0].clips[0];
  const hitOn = (range, closed) => ({
    clip: parent,
    row: { kind: "track", id: "A", index: 0 },
    gate: { trackId: "A", clipId: "p", range, closed, implicit: true },
  });

  test("a closed portion is opened as a muted clip first, so it stays silent", () => {
    assert.deepEqual(portionDragEdit(silenced, hitOn([4 * S, 6 * S], true), new Set(["p"])), {
      op: "open_gated_region",
      args: { track_id: "A", clip_id: "p", at: 5 * S, muted: true },
      coalesce: `portion-drag:p:${5 * S}`,
    });
  });
  test("an open portion is opened as a sounding clip", () => {
    const edit = portionDragEdit(silenced, hitOn([6 * S, 10 * S], false), new Set());
    assert.deepEqual(edit.args, { track_id: "A", clip_id: "p", at: 8 * S, muted: false });
  });
  test("a press off any portion, or a stale range, drags the clip as before", () => {
    const plain = { clip: parent, row: { kind: "track", id: "A", index: 0 }, gate: null };
    assert.equal(portionDragEdit(silenced, plain, new Set()), null);
    assert.equal(portionDragEdit(silenced, hitOn([3 * S, 6 * S], true), new Set()), null);
  });
  test("a selection of several clips, or a group, moves as it is", () => {
    assert.equal(portionDragEdit(silenced, hitOn([4 * S, 6 * S], true), new Set(["p", "q"])), null);
    const grouped = {
      ...silenced,
      tracks: [
        {
          ...silenced.tracks[0],
          clips: silenced.tracks[0].clips.map((clip) => ({ ...clip, group: "g" })),
        },
      ],
    };
    assert.equal(portionDragEdit(grouped, hitOn([4 * S, 6 * S], true), new Set()), null);
  });
});
