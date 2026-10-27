import assert from "node:assert/strict";
import { test } from "node:test";
import { LUFS_TICKS, lufsToX, shortTermLevel } from "../level-meter.js";

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
