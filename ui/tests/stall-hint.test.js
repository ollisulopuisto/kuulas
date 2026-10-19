import assert from "node:assert/strict";
import test from "node:test";
import { quietSeconds, stallState } from "../stall-hint.js";

test("stallState: empty samples return 'moving'", () => {
  assert.equal(stallState([], 1000), "moving");
  assert.equal(stallState(null, 1000), "moving");
  assert.equal(stallState(undefined, 1000), "moving");
  assert.equal(quietSeconds([], 1000), 0);
  assert.equal(quietSeconds(null, 1000), 0);
});

test("stallState: single sample progression across quiet and stuck thresholds", () => {
  const samples = [{ t: 1000, progress: 50, message: "Mastering…" }];

  // Moving: less than quietMs (15000 ms)
  assert.equal(stallState(samples, 1000), "moving");
  assert.equal(stallState(samples, 15999), "moving"); // elapsed = 14999 ms
  assert.equal(quietSeconds(samples, 15999), 0);

  // Quiet: between 15000 ms and 89999 ms
  assert.equal(stallState(samples, 16000), "quiet"); // elapsed = 15000 ms
  assert.equal(quietSeconds(samples, 16000), 15);
  assert.equal(stallState(samples, 50450), "quiet"); // elapsed = 49450 ms
  assert.equal(quietSeconds(samples, 50450), 49);
  assert.equal(stallState(samples, 90999), "quiet"); // elapsed = 89999 ms
  assert.equal(quietSeconds(samples, 90999), 89);

  // Stuck: at 90000 ms or more
  assert.equal(stallState(samples, 91000), "stuck"); // elapsed = 90000 ms
  assert.equal(quietSeconds(samples, 91000), 90);
  assert.equal(stallState(samples, 150000), "stuck");
  assert.equal(quietSeconds(samples, 150000), 149);
});

test("stallState: progress change resets the inactivity timer", () => {
  const samples = [
    { t: 0, progress: 10, message: "Analyzing" },
    { t: 10000, progress: 20, message: "Analyzing" },
    { t: 20000, progress: 30, message: "Analyzing" }, // last change at t = 20000
    { t: 30000, progress: 30, message: "Analyzing" },
  ];

  // At now = 34000: elapsed since t=20000 is 14000 ms (< 15000 ms) -> moving
  assert.equal(stallState(samples, 34000), "moving");
  assert.equal(quietSeconds(samples, 34000), 0);

  // At now = 36000: elapsed since t=20000 is 16000 ms (>= 15000 ms) -> quiet
  assert.equal(stallState(samples, 36000), "quiet");
  assert.equal(quietSeconds(samples, 36000), 16);

  // At now = 111000: elapsed since t=20000 is 91000 ms (>= 90000 ms) -> stuck
  assert.equal(stallState(samples, 111000), "stuck");
  assert.equal(quietSeconds(samples, 111000), 91);
});

test("stallState: message change alone counts as activity", () => {
  const samples = [
    { t: 0, progress: 87.5, message: "Pass 1" },
    { t: 20000, progress: 87.5, message: "Pass 1" },
    { t: 40000, progress: 87.5, message: "Pass 2" }, // message changed at t = 40000!
    { t: 50000, progress: 87.5, message: "Pass 2" },
  ];

  // Elapsed since t=40000 at now=54000 is 14000 ms (< 15000 ms) -> moving
  assert.equal(stallState(samples, 54000), "moving");
  assert.equal(quietSeconds(samples, 54000), 0);

  // At now = 56000: elapsed since t=40000 is 16000 ms -> quiet
  assert.equal(stallState(samples, 56000), "quiet");
  assert.equal(quietSeconds(samples, 56000), 16);
});

test("stallState: custom quietMs and stuckMs options", () => {
  const samples = [{ t: 1000, progress: 10, message: "Running" }];
  const options = { quietMs: 5000, stuckMs: 20000 };

  assert.equal(stallState(samples, 5000, options), "moving"); // 4000 ms
  assert.equal(stallState(samples, 6000, options), "quiet"); // 5000 ms
  assert.equal(stallState(samples, 21000, options), "stuck"); // 20000 ms
  assert.equal(quietSeconds(samples, 21000, options), 20);
});

test("stallState: throws Error when now is before the last sample", () => {
  const samples = [
    { t: 1000, progress: 10, message: "A" },
    { t: 5000, progress: 20, message: "B" },
  ];

  assert.throws(() => stallState(samples, 4999), /before/i);
  assert.throws(() => quietSeconds(samples, 4999), /before/i);
});

test("stallState: inputs are never mutated", () => {
  const samples = Object.freeze([
    Object.freeze({ t: 1000, progress: 50, message: "Work" }),
    Object.freeze({ t: 2000, progress: 50, message: "Work" }),
  ]);
  const options = Object.freeze({ quietMs: 15000, stuckMs: 90000 });

  assert.equal(stallState(samples, 20000, options), "quiet");
  assert.equal(quietSeconds(samples, 20000, options), 19);
});
