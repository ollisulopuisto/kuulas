import assert from "node:assert/strict";
import test from "node:test";
import { createLiveWave } from "../live-wave.js";

test("createLiveWave: fill up to columns", () => {
  const wave = createLiveWave({ columns: 4 });
  assert.deepEqual(wave.snapshot(), []);

  wave.push(0.2);
  assert.deepEqual(wave.snapshot(), [0.2]);

  wave.push(0.5);
  wave.push(0.8);
  assert.deepEqual(wave.snapshot(), [0.2, 0.5, 0.8]);

  wave.push(1.0);
  assert.deepEqual(wave.snapshot(), [0.2, 0.5, 0.8, 1.0]);
});

test("createLiveWave: slide sliding window drops oldest", () => {
  const wave = createLiveWave({ columns: 3 });
  wave.push(0.1);
  wave.push(0.2);
  wave.push(0.3);
  assert.deepEqual(wave.snapshot(), [0.1, 0.2, 0.3]);

  wave.push(0.4);
  assert.deepEqual(wave.snapshot(), [0.2, 0.3, 0.4]);

  wave.push(0.5);
  assert.deepEqual(wave.snapshot(), [0.3, 0.4, 0.5]);
});

test("createLiveWave: clamping values outside 0..1", () => {
  const wave = createLiveWave({ columns: 4 });
  wave.push(-0.5);
  wave.push(-100);
  wave.push(1.5);
  wave.push(999);
  assert.deepEqual(wave.snapshot(), [0, 0, 1, 1]);
});

test("createLiveWave: NaN becomes 0", () => {
  const wave = createLiveWave({ columns: 3 });
  wave.push(Number.NaN);
  wave.push(0.5);
  wave.push("not-a-number");
  assert.deepEqual(wave.snapshot(), [0, 0.5, 0]);
});

test("createLiveWave: snapshot independence", () => {
  const wave = createLiveWave({ columns: 3 });
  wave.push(0.3);
  wave.push(0.7);

  const snap1 = wave.snapshot();
  assert.deepEqual(snap1, [0.3, 0.7]);

  // Mutating snap1 should not affect wave
  snap1.push(0.9);
  snap1[0] = 0.0;

  const snap2 = wave.snapshot();
  assert.deepEqual(snap2, [0.3, 0.7]);
});

test("createLiveWave: reset empties buffer", () => {
  const wave = createLiveWave({ columns: 3 });
  wave.push(0.4);
  wave.push(0.6);
  assert.equal(wave.snapshot().length, 2);

  wave.reset();
  assert.deepEqual(wave.snapshot(), []);

  wave.push(0.8);
  assert.deepEqual(wave.snapshot(), [0.8]);
});

test("createLiveWave: columns less than 1 throws RangeError", () => {
  assert.throws(() => createLiveWave({ columns: 0 }), RangeError);
  assert.throws(() => createLiveWave({ columns: -5 }), RangeError);
  assert.throws(() => createLiveWave({ columns: -0.5 }), RangeError);
  assert.throws(() => createLiveWave({ columns: "three" }), RangeError);
  assert.throws(() => createLiveWave({}), RangeError);
});
