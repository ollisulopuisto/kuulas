import assert from "node:assert/strict";
import test from "node:test";
import { NUDGE_STEPS_MS, nextStep, nudgeFrames } from "../nudge-steps.js";

test("NUDGE_STEPS_MS: contains expected values", () => {
  assert.deepEqual(NUDGE_STEPS_MS, [1, 10, 100, 1000]);
});

test("nudgeFrames: frame calculation, rounding, min 1 frame, non-positive and non-finite", () => {
  // 48000 Hz:
  // 1000 ms -> 48000
  assert.equal(nudgeFrames(1000, 48000), 48000);
  // 100 ms -> 4800
  assert.equal(nudgeFrames(100, 48000), 4800);
  // 10 ms -> 480
  assert.equal(nudgeFrames(10, 48000), 480);
  // 1 ms -> 48
  assert.equal(nudgeFrames(1, 48000), 48);

  // 44100 Hz:
  // 1 ms -> 44.1 -> 44
  assert.equal(nudgeFrames(1, 44100), 44);

  // Small positive step rounds to 0 but must be at least 1
  assert.equal(nudgeFrames(0.001, 48000), 1);
  assert.equal(nudgeFrames(0.00001, 48000), 1);

  // Zero and negative stepMs or rate
  assert.equal(nudgeFrames(0, 48000), 0);
  assert.equal(nudgeFrames(-10, 48000), 0);
  assert.equal(nudgeFrames(100, 0), 0);
  assert.equal(nudgeFrames(100, -48000), 0);

  // Non-finite and non-number
  assert.equal(nudgeFrames(Number.POSITIVE_INFINITY, 48000), 0);
  assert.equal(nudgeFrames(100, Number.POSITIVE_INFINITY), 0);
  assert.equal(nudgeFrames(Number.NaN, 48000), 0);
  assert.equal(nudgeFrames(100, Number.NaN), 0);
  assert.equal(nudgeFrames("100", 48000), 0);
  assert.equal(nudgeFrames(null, 48000), 0);
});

test("nextStep: stepping up, down, clamping, snapping off-list values, ties to smaller", () => {
  // Direction > 0 (stepping up)
  assert.equal(nextStep(1, 1), 10);
  assert.equal(nextStep(10, 1), 100);
  assert.equal(nextStep(100, 1), 1000);
  assert.equal(nextStep(1000, 1), 1000); // Clamped at top

  // Direction < 0 (stepping down)
  assert.equal(nextStep(1000, -1), 100);
  assert.equal(nextStep(100, -1), 10);
  assert.equal(nextStep(10, -1), 1);
  assert.equal(nextStep(1, -1), 1); // Clamped at bottom

  // Direction 0 returns the snapped value
  assert.equal(nextStep(1, 0), 1);
  assert.equal(nextStep(10, 0), 10);
  assert.equal(nextStep(100, 0), 100);
  assert.equal(nextStep(1000, 0), 1000);

  // Snapping values not in the list:
  // 50: |50 - 10| = 40, |50 - 100| = 50 -> nearest is 10
  assert.equal(nextStep(50, 0), 10);
  assert.equal(nextStep(50, 1), 100);
  assert.equal(nextStep(50, -1), 1);

  // 80: |80 - 10| = 70, |80 - 100| = 20 -> nearest is 100
  assert.equal(nextStep(80, 0), 100);
  assert.equal(nextStep(80, 1), 1000);
  assert.equal(nextStep(80, -1), 10);

  // Ties go to the smaller:
  // Between 10 and 100: midpoint is 55. |55 - 10| = 45, |55 - 100| = 45 -> tie -> snaps to 10
  assert.equal(nextStep(55, 0), 10);
  assert.equal(nextStep(55, 1), 100);
  assert.equal(nextStep(55, -1), 1);

  // Value below 1 snaps to 1
  assert.equal(nextStep(0, 0), 1);
  assert.equal(nextStep(-10, 0), 1);
  assert.equal(nextStep(-10, 1), 10);

  // Value above 1000 snaps to 1000
  assert.equal(nextStep(5000, 0), 1000);
  assert.equal(nextStep(5000, -1), 100);
  assert.equal(nextStep(5000, 1), 1000);
});
