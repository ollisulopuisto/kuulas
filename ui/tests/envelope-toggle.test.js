import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  envelopeChange,
  envelopeDragChange,
  envelopeMove,
  envelopePointZone,
  envelopeToggle,
} from "../gain-drag.js";
import { dbToY } from "../lanes.js";

const ROW = 80;
// Envelope frames are SOURCE frames; the clip starts at 1000 on the timeline and plays from
// source frame 200, so timeline frame 1500 is source frame 700.
const clip = (extra = {}) => ({
  id: "c1",
  start: 1000,
  offset: 200,
  length: 5000,
  gain_db: 0,
  envelope: [],
  ...extra,
});
const at = (c, timelineFrame, db, extra = {}) => ({
  timelineFrame,
  rowHeight: ROW,
  rowY: dbToY((c.gain_db ?? 0) + db, ROW),
  point: null,
  ...extra,
});

describe("double-click on a clip's gain line", () => {
  test("on the flat line it adds a point at 0 dB, in source frames", () => {
    const c = clip();
    assert.deepEqual(envelopeToggle(c, at(c, 1500, 0)), { points: [[700, 0]], action: "added" });
  });
  test("on a sloping envelope the new point sits on the line", () => {
    const c = clip({
      envelope: [
        [200, 0],
        [1200, -10],
      ],
    });
    const result = envelopeToggle(c, at(c, 1500, -3));
    assert.equal(result.action, "added");
    assert.deepEqual(result.points, [
      [200, 0],
      [700, -5],
      [1200, -10],
    ]);
  });
  test("the point's dB is relative to the clip gain", () => {
    const c = clip({ gain_db: -6 });
    assert.deepEqual(envelopeToggle(c, at(c, 1500, 0)).points, [[700, 0]]);
  });
  test("away from the line it does nothing (other double-clicks are unaffected)", () => {
    const c = clip();
    assert.equal(envelopeToggle(c, { ...at(c, 1500, 0), rowY: dbToY(0, ROW) + 30 }), null);
  });
  test("a lane too short for the line does nothing", () => {
    const c = clip();
    assert.equal(envelopeToggle(c, { ...at(c, 1500, 0), rowHeight: 30 }), null);
  });
  test("on an existing point it removes that point", () => {
    const c = clip({
      envelope: [
        [200, 0],
        [700, -4],
        [1200, 0],
      ],
    });
    assert.deepEqual(envelopeToggle(c, at(c, 1502, -4, { point: 1 })), {
      points: [
        [200, 0],
        [1200, 0],
      ],
      action: "removed",
    });
  });
  test("it does not change the clip it was given", () => {
    const c = clip({ envelope: [[200, 0]] });
    envelopeToggle(c, at(c, 1500, 0));
    assert.deepEqual(c.envelope, [[200, 0]]);
  });
});

describe("the envelope edit", () => {
  test("is one set_clip_envelope with the points", () => {
    const change = envelopeChange("c1", [[700, 0]]);
    assert.equal(change.op, "set_clip_envelope");
    assert.deepEqual(change.args, { clip_id: "c1", points: [[700, 0]] });
    assert.equal(change.labelKey, "ui.clipdrag.envelope");
  });

  test("moves a point in source frames and keeps the pointer's grab offset", () => {
    const c = clip({
      envelope: [
        [200, 0],
        [1200, -10],
        [2200, 0],
      ],
    });
    const points = envelopeMove(c, 1, {
      timelineFrame: 1700,
      rowHeight: ROW,
      rowY: dbToY(-14, ROW),
      grabFrames: -400,
      grabY: 3,
    });

    assert.deepEqual(points, [
      [200, 0],
      [1300, -12.2],
      [2200, 0],
    ]);
  });

  test("a hit envelope point starts a point drag, not a clip drag", () => {
    const c = clip({ envelope: [[700, -5]] });
    assert.deepEqual(
      envelopePointZone({
        clip: c,
        row: { kind: "track" },
        edge: null,
        point: 0,
      }),
      { kind: "envelope", point: 0 },
    );
  });

  test("an envelope drag is one coalesced clip edit", () => {
    const change = envelopeDragChange("c1", [[700, -5]]);
    assert.equal(change.coalesce, "clip-envelope-c1");
  });
});
