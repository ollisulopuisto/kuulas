import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  fadeChange,
  fadeFromX,
  fadeHandleAt,
  fadeHandles,
  fadeShape,
  gainChange,
  gainFromY,
  gainGrab,
  gainLineHit,
  gainLineVisible,
} from "../gain-drag.js";
import { dbToY } from "../lanes.js";

const H = 80;
const clip = { id: "c", start: 0, length: 1000, gain_db: -6, fade_in: 0, fade_out: 0 };

describe("gain line", () => {
  test("is hit within a few pixels of its level, not elsewhere", () => {
    const y = dbToY(-6, H);
    assert.equal(gainLineHit(clip, H, y), true);
    assert.equal(gainLineHit(clip, H, y + 4), true);
    assert.equal(gainLineHit(clip, H, y + 9), false);
  });
  test("is not drawn, so not hit, in a lane too short for it", () => {
    assert.equal(gainLineHit(clip, 30, dbToY(-6, 30)), false);
  });
  test("is visible when it says something or the clip is selected", () => {
    assert.equal(gainLineVisible({ gain_db: 0 }, false), false);
    assert.equal(gainLineVisible({ gain_db: 0 }, true), true);
    assert.equal(gainLineVisible({ gain_db: -3 }, false), true);
    assert.equal(gainLineVisible({ gain_db: 0, envelope: [[0, 0]] }, false), true);
  });
  test("gain follows the pointer keeping the grab point on the line", () => {
    const y0 = dbToY(-6, H) + 3; // grabbed 3 px below the line
    const grab = gainGrab(clip, H, y0);
    assert.equal(gainFromY(H, y0, grab), -6);
    const up = gainFromY(H, y0 - 10, grab);
    assert.ok(up > -6);
    assert.equal(up, Math.round(up * 10) / 10);
  });
  test("is limited to the lane's range, +12 to -30 dB", () => {
    assert.equal(gainFromY(H, -50, 0), 12);
    assert.equal(gainFromY(H, 500, 0), -30);
  });
  test("is one coalesced set_clip per clip", () => {
    const c = gainChange("c", -4.5);
    assert.equal(c.op, "set_clip");
    assert.deepEqual(c.args, { clip_id: "c", gain_db: -4.5 });
    assert.equal(c.coalesce, "clip-gain-c");
    assert.equal(c.labelKey, "ui.clipdrag.gain");
  });
});

describe("fade handles", () => {
  const frame = { left: 100, right: 400, zoom: 1 };
  test("sit at the fade's end, at least an inset in from the corner", () => {
    const h = fadeHandles({ ...clip, fade_in: 50, fade_out: 0 }, frame);
    assert.equal(h.in.x, 150);
    assert.ok(h.out.x < 400 && h.out.x > 380);
    assert.equal(h.in.y, h.out.y);
  });
  test("are hit near the handle, in or out, or neither", () => {
    const h = fadeHandles(clip, frame);
    assert.equal(fadeHandleAt(clip, frame, h.in.x, h.in.y, H), "in");
    assert.equal(fadeHandleAt(clip, frame, h.out.x, h.out.y, H), "out");
    assert.equal(fadeHandleAt(clip, frame, 250, h.in.y, H), null);
    assert.equal(fadeHandleAt(clip, frame, h.in.x, h.in.y + 30, H), null);
  });
  test("not in a short lane or a clip too narrow for two handles", () => {
    const h = fadeHandles(clip, frame);
    assert.equal(fadeHandleAt(clip, frame, h.in.x, h.in.y, 30), null);
    const narrow = { left: 100, right: 120, zoom: 1 };
    const n = fadeHandles(clip, narrow);
    assert.equal(fadeHandleAt(clip, narrow, n.in.x, n.in.y, H), null);
  });
  test("fade length follows the pointer's travel, from where the fade was", () => {
    const base = { startFade: 50, startX: 150, zoom: 2 };
    assert.equal(fadeFromX(clip, "in", { ...base, x: 160 }), 70);
    assert.equal(fadeFromX(clip, "in", { ...base, x: 100 }), 0);
    assert.equal(fadeFromX(clip, "out", { ...base, x: 160 }), 30);
  });
  test("is limited by the clip length less the other fade", () => {
    const c = { ...clip, fade_out: 300 };
    const base = { startFade: 0, startX: 0, zoom: 1, x: 5000 };
    assert.equal(fadeFromX(c, "in", base), 700);
    assert.equal(fadeFromX(c, "out", { ...base, x: -5000 }), 1000);
  });
  test("shape is a line from the clip's bottom corner up to the fade's end", () => {
    const shape = fadeShape({ ...clip, fade_in: 50 }, "in", { ...frame, top: 20, height: 60 });
    assert.deepEqual(shape, [
      [100, 80],
      [150, 20],
    ]);
    const out = fadeShape({ ...clip, fade_out: 50 }, "out", { ...frame, top: 20, height: 60 });
    assert.deepEqual(out, [
      [400, 80],
      [350, 20],
    ]);
  });
  test("is one coalesced set_clip per field, like the inspector's", () => {
    const c = fadeChange("c", "out", 123);
    assert.equal(c.op, "set_clip");
    assert.deepEqual(c.args, { clip_id: "c", fade_out: 123 });
    assert.equal(c.coalesce, "clip-fade_out-c");
    assert.equal(c.labelKey, "ui.clipdrag.fade_out");
  });
});
