// Dragging a clipboard entry from the Clipboard tab onto the timeline (ROADMAP "Drag clips from
// the Clipboard panel onto the timeline", docs/design/CLIPBOARD-SHELVES.md): where it lands,
// the outlines drawn while dragging, and the controller that adopts a foreign entry first and
// then pastes it as one edit.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  CLIP_DRAG_TYPE,
  createClipboardDrag,
  dropOutlines,
  dropTarget,
  isClipboardDrag,
} from "../clipboard-drag.js";
import { RULER_HEIGHT } from "../lanes.js";

const S = 48000;
const ZOOM = 1000; // frames per pixel
const view = { scroll: 0, zoom: ZOOM, scrollY: 0 };
const layout = {
  height: 200,
  rows: [
    { kind: "track", id: "A", top: 0, height: 80 },
    { kind: "track", id: "V", top: 80, height: 80 },
    { kind: "gap", id: "gap:2", top: 160, height: 14 },
  ],
};
const project = {
  rate: S,
  tracks: [
    { id: "A", clips: [{ id: "a1", start: 100_000, length: 50_000 }] },
    { id: "V", clips: [] },
  ],
};
const entry = {
  id: "e1",
  slots: 2,
  clips: 2,
  length: 30_000,
  refs: [
    { rel_start: 0, length: 20_000, track_slot: 0 },
    { rel_start: 10_000, length: 20_000, track_slot: 1 },
  ],
};
const marks = { playhead: 400_000, inPoint: null, outPoint: null };
const at = (x, y, alt = false, extra = {}) =>
  dropTarget({ x, y: RULER_HEIGHT + y, alt }, { layout, project, view, entry, marks, ...extra });

describe("what a drag carries", () => {
  test("only a drag with the clipboard's type is one of ours", () => {
    assert.equal(isClipboardDrag({ types: [CLIP_DRAG_TYPE] }), true);
    assert.equal(isClipboardDrag({ types: ["Files"] }), false);
    assert.equal(isClipboardDrag(null), false);
  });
});

describe("where a drop lands", () => {
  test("on a lane: that track, the frame under the pointer; the slots go on downwards", () => {
    const target = at(300, 10);
    assert.equal(target.trackId, "A");
    assert.equal(target.at, 300_000);
    assert.deepEqual(target.targetTracks, { 0: "A", 1: "V" });
    assert.equal(at(300, 90).trackId, "V");
    assert.deepEqual(at(300, 90).targetTracks, { 0: "V", 1: "V" });
  });

  test("the ruler, a gap and the empty space below are no place to drop", () => {
    assert.equal(dropTarget({ x: 300, y: 5 }, { layout, project, view, entry, marks }), null);
    assert.equal(at(300, 165), null);
    assert.equal(at(300, 400), null);
  });

  test("the start snaps to clip edges and the playhead within 8 px, as moving clips does", () => {
    const near = at(155, 10); // 155 000, 5 px from the clip's end at 150 000
    assert.equal(near.at, 150_000);
    assert.equal(near.snapAt, 150_000);
    assert.equal(at(396, 10).at, 400_000); // the playhead
    assert.equal(at(300, 10).snapAt, null);
  });

  test("the end snaps too: the block's last frame meets an edge", () => {
    // Entry 30 000 long dropped at 72 000 ends at 102 000, 2 px from the clip's start.
    assert.equal(at(72, 10).at, 70_000);
  });

  test("Alt: no snapping, and a start inside a clip stops at that clip's end", () => {
    assert.equal(at(155, 10, true).at, 155_000); // no snap to the edge 5 px away
    assert.equal(at(120, 10, true).at, 150_000);
    assert.equal(at(120, 90, true).at, 120_000); // nothing on that track
  });

  test("never before the start of the timeline", () => {
    assert.equal(at(-50, 10, true, { view: { ...view, scroll: 0 } }).at, 0);
  });
});

describe("the outlines while dragging", () => {
  test("one per clip, on the tracks the slots go to, keeping the layout", () => {
    const target = at(300, 10);
    const { outlines, rows } = dropOutlines(entry, target, { layout, view });
    assert.deepEqual(outlines, [
      { x: 300, y: RULER_HEIGHT, w: 20, h: 80 },
      { x: 310, y: RULER_HEIGHT + 80, w: 20, h: 80 },
    ]);
    assert.deepEqual(rows, [{ y: RULER_HEIGHT, h: 80 }]);
  });

  test("an entry without references is one outline of its length on the track", () => {
    const target = at(300, 10);
    const { outlines } = dropOutlines({ id: "x", slots: 1, length: 30_000 }, target, {
      layout,
      view: { ...view, scrollY: 10 },
    });
    assert.deepEqual(outlines, [{ x: 300, y: RULER_HEIGHT - 10, w: 30, h: 80 }]);
  });
});

describe("the controller", () => {
  function setup({ adopted = { id: "new" }, pasteMode = "overwrite" } = {}) {
    const calls = [];
    let target = { trackId: "A", at: 300_000, targetTracks: { 0: "A", 1: "V" } };
    const drag = createClipboardDrag({
      getState: () => ({ pasteMode }),
      timeline: {
        clipboardDropTarget: (event, dragged) => (event.off ? null : { ...target, dragged }),
        setClipboardDropPreview: (preview) =>
          calls.push(["preview", preview ? preview.target.at : null]),
      },
      adopt: async (dragged, source) => {
        calls.push(["adopt", dragged.id, source.shelf, source.from]);
        return adopted;
      },
      paste: (args, dragged) => calls.push(["paste", args, dragged.id]),
    });
    return {
      drag,
      calls,
      move: (next) => {
        target = { ...target, ...next };
      },
    };
  }
  const event = (extra = {}) => ({
    dataTransfer: { types: [CLIP_DRAG_TYPE], dropEffect: "" },
    preventDefault() {
      this.prevented = true;
    },
    ...extra,
  });

  test("over the timeline it accepts the drop and draws the preview; without a drag it does not", () => {
    const { drag, calls } = setup();
    const before = event();
    assert.equal(drag.over(before), false);
    assert.equal(before.prevented, undefined);
    drag.start(entry, { shelf: "project", from: "" });
    const over = event();
    assert.equal(drag.over(over), true);
    assert.equal(over.prevented, true);
    assert.equal(over.dataTransfer.dropEffect, "copy");
    assert.deepEqual(calls, [["preview", 300_000]]);
    assert.equal(drag.over(event({ off: true })), false);
    assert.deepEqual(calls.at(-1), ["preview", null]);
  });

  test("a project entry is pasted at once, in the paste mode chosen in the panel", async () => {
    const { drag, calls } = setup({ pasteMode: "insert" });
    drag.start(entry, { shelf: "project", from: "" });
    assert.equal(await drag.drop(event()), true);
    assert.deepEqual(calls.at(-1), [
      "paste",
      { entry_id: "e1", at: 300_000, mode: "insert", target_tracks: { 0: "A", 1: "V" } },
      "e1",
    ]);
    assert.ok(calls.some((call) => call[0] === "preview" && call[1] === null));
    assert.equal(drag.active(), false);
  });

  test("an entry of another shelf is adopted first, then the copy is pasted", async () => {
    const { drag, calls } = setup();
    drag.start(entry, { shelf: "series", from: "" });
    await drag.drop(event());
    assert.deepEqual(
      calls.filter((call) => call[0] !== "preview"),
      [
        ["adopt", "e1", "series", ""],
        [
          "paste",
          { entry_id: "new", at: 300_000, mode: "overwrite", target_tracks: { 0: "A", 1: "V" } },
          "e1",
        ],
      ],
    );
  });

  test("a failed adopt pastes nothing", async () => {
    const { drag, calls } = setup({ adopted: null });
    drag.start(entry, { shelf: "other", from: "/x/Ep.kuulas" });
    assert.equal(await drag.drop(event()), false);
    assert.equal(calls.filter((call) => call[0] === "paste").length, 0);
  });

  test("a drop off the timeline, or after Esc (dragend), pastes nothing", async () => {
    const { drag, calls } = setup();
    drag.start(entry, { shelf: "project", from: "" });
    assert.equal(await drag.drop(event({ off: true })), false);
    drag.start(entry, { shelf: "project", from: "" });
    drag.end();
    assert.equal(drag.active(), false);
    assert.equal(await drag.drop(event()), false);
    assert.equal(calls.filter((call) => call[0] === "paste").length, 0);
  });
});

describe("clipboard automation snapping", () => {
  const automated = {
    ...project,
    tracks: project.tracks.map((track) => ({
      ...track,
      automation: [
        [300_000, 0],
        [320_000, -9],
      ],
    })),
  };
  const target = (mod, alt = false, x = 304, extraMarks = marks) =>
    dropTarget(
      { x, y: RULER_HEIGHT + 10, mod, alt },
      { layout, project: automated, view, entry, marks: extraMarks },
    );

  test("only the held modifier adds automation targets and preview marks", () => {
    assert.equal(target(false).at, 304_000);
    assert.deepEqual(target(false).autoMarks, []);
    assert.equal(target(true).at, 300_000);
    assert.deepEqual(target(true).autoMarks, [300_000, 320_000]);
    assert.equal(target(false).at, 304_000);
  });
  test("primary targets win and Alt disables automation snap and marks", () => {
    assert.equal(target(true, false, 301, { playhead: 307_000 }).at, 307_000);
    assert.equal(target(true, true).at, 304_000);
    assert.deepEqual(target(true, true).autoMarks, []);
  });
  for (const ending of ["drop", "end"]) {
    test(`${ending} clears preview automation marks`, async () => {
      let preview = null;
      const drag = createClipboardDrag({
        getState: () => ({}),
        timeline: {
          clipboardDropTarget: () => target(true),
          setClipboardDropPreview: (next) => {
            preview = next;
          },
        },
        paste: () => {},
      });
      drag.start(entry);
      const event = { dataTransfer: { types: [CLIP_DRAG_TYPE] }, preventDefault() {} };
      drag.over(event);
      assert.deepEqual(preview.target.autoMarks, [300_000, 320_000]);
      await drag[ending](event);
      assert.equal(preview, null);
    });
  }
});
