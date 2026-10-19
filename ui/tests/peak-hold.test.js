import assert from "node:assert/strict";
import test from "node:test";
import { createPeakHold } from "../peak-hold.js";

test("createPeakHold: jump up immediately to level", () => {
  const ph = createPeakHold();
  const res = ph.update(-10, 0);
  assert.equal(res.bar, -10);
  assert.equal(res.peak, -10);
  assert.equal(res.clipped, false);
});

test("createPeakHold: fall rate over 1 s gives -20 dB", () => {
  const ph = createPeakHold();
  ph.update(-10, 0);

  // 1 second later with silence (-60 dB)
  const res = ph.update(-60, 1000);
  assert.equal(res.bar, -30); // fell from -10 by 20 dB over 1000 ms
});

test("createPeakHold: hold for 1.5 s then the fall", () => {
  const ph = createPeakHold();
  ph.update(-10, 0);

  // Still within 1.5 s hold (at 1500 ms)
  const resHold = ph.update(-60, 1500);
  assert.equal(resHold.peak, -10);

  // 1 s after hold ended (at 2500 ms): falls by 20 dB to -30 dB
  const resFall = ph.update(-60, 2500);
  assert.equal(resFall.peak, -30);
});

test("createPeakHold: floor clamp", () => {
  const ph = createPeakHold({ floorDb: -60 });
  ph.update(-50, 0);

  // Long silence (10 seconds): decays past floor, clamped to -60 dB
  const res = ph.update(-60, 10000);
  assert.equal(res.bar, -60);
  assert.equal(res.peak, -60);
});

test("createPeakHold: silence inputs (-Infinity, NaN, < floorDb)", () => {
  const ph = createPeakHold();

  // -Infinity treated as silence (floorDb = -60)
  const res1 = ph.update(-Infinity, 0);
  assert.equal(res1.bar, -60);
  assert.equal(res1.peak, -60);

  // NaN treated as silence
  const res2 = ph.update(Number.NaN, 100);
  assert.equal(res2.bar, -60);
  assert.equal(res2.peak, -60);

  // Values below floorDb clamped to floorDb
  const res3 = ph.update(-90, 200);
  assert.equal(res3.bar, -60);
  assert.equal(res3.peak, -60);
});

test("createPeakHold: clip stays latched until clearClip()", () => {
  const ph = createPeakHold();

  // Level above 0 dBFS sets clipped: true and clamps bar/peak to 0
  const res1 = ph.update(0.5, 0);
  assert.equal(res1.clipped, true);
  assert.equal(res1.bar, 0);
  assert.equal(res1.peak, 0);

  // Later update with normal level keeps clipped: true
  const res2 = ph.update(-12, 500);
  assert.equal(res2.clipped, true);

  // clearClip() clears it
  ph.clearClip();
  const res3 = ph.update(-12, 600);
  assert.equal(res3.clipped, false);
});

test("createPeakHold: time going backwards treated as no time passing", () => {
  const ph = createPeakHold();
  ph.update(-10, 1000);

  // Time going backward to 500 ms
  const res = ph.update(-60, 500);
  assert.equal(res.bar, -10); // no decay applied
  assert.equal(res.peak, -10);
});

test("createPeakHold: reset clears everything", () => {
  const ph = createPeakHold();
  ph.update(1.2, 0); // clipped, level at 0
  assert.equal(ph.update(1.2, 0).clipped, true);

  ph.reset();

  const res = ph.update(-20, 1000);
  assert.equal(res.bar, -20);
  assert.equal(res.peak, -20);
  assert.equal(res.clipped, false);
});

test("createPeakHold: custom holdMs and decayDbPerS", () => {
  const ph = createPeakHold({ holdMs: 1000, decayDbPerS: 10, floorDb: -40 });
  ph.update(-10, 0);

  // At 1000 ms: hold ends
  assert.equal(ph.update(-40, 1000).peak, -10);

  // At 2000 ms: 1 s after hold, falls by 10 dB to -20 dB
  assert.equal(ph.update(-40, 2000).peak, -20);
});
