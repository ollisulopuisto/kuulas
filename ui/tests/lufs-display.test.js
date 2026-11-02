import assert from "node:assert/strict";
import { test } from "node:test";
import { createLevelMeter, LUFS_TICKS, lufsToX, shortTermLevel } from "../level-meter.js";

test("the loudness display uses the three-second field, never peak or RMS", () => {
  assert.equal(shortTermLevel({ short_term: -23, l: -1, r: -2, rms_l: -9 }), -23);
  assert.equal(shortTermLevel({ l: -1, r: -2 }), null);
  assert.equal(shortTermLevel({ short_term: null }), null);
  assert.equal(shortTermLevel({ short_term: Number.NaN }), null);
});

test("the loudness scale has labelled -23 and -16 reference marks", () => {
  assert.deepEqual(LUFS_TICKS, [-23, -16]);
  assert.ok(lufsToX(-23, 160) < lufsToX(-16, 160));
  assert.equal(lufsToX(-90, 160), 0);
  assert.equal(lufsToX(0, 160), 160);
});

test("the graphical LUFS meter stays visible at rest and follows loudness during playback", () => {
  const fill = { style: {}, dataset: {} };
  const readout = {};
  const ticks = LUFS_TICKS.map((value) => ({ dataset: { lufs: value }, style: {} }));
  const bars = {
    hidden: true,
    clientWidth: 140,
    querySelector: () => fill,
    querySelectorAll: () => ticks,
  };
  const root = {
    querySelectorAll: () => [],
    hidden: true,
    querySelector: (selector) => (selector === ".lm-readout" ? readout : null),
  };
  const clipButton = { hidden: true, addEventListener() {} };
  const meter = createLevelMeter({ root, bars, clipButton });
  meter.playing(false);
  assert.equal(root.hidden, false, "stopping must not remove the meter");
  assert.equal(bars.hidden, false);
  assert.equal(readout.hidden, false);
  assert.equal(fill.style.width, "0px");
  meter.frame({ short_term: -23, l: -1, r: -2, hold_l: -1, hold_r: -2 });
  assert.equal(fill.style.width, `${lufsToX(-23, 140)}px`);
  meter.frame({ short_term: -16, l: -40, r: -40, hold_l: -40, hold_r: -40 });
  assert.equal(fill.style.width, `${lufsToX(-16, 140)}px`, "bar follows LUFS, not peaks");
  assert.deepEqual(
    ticks.map((tick) => tick.style.left),
    LUFS_TICKS.map((value) => `${lufsToX(value, 100)}%`),
  );
  meter.playing(false);
  assert.equal(root.hidden, false);
  assert.equal(bars.hidden, false);
  assert.equal(fill.style.width, "0px");
});
