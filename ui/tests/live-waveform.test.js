import assert from "node:assert/strict";
import { test } from "node:test";
import { liveWaveformColumns } from "../live-take.js";

test("live waveforms obey the same half/full display as finished clips", () => {
  assert.deepEqual([...liveWaveformColumns([0.5], { mode: "half", height: 100 })], [50, 100]);
  assert.deepEqual([...liveWaveformColumns([0.5], { mode: "full", height: 100 })], [25, 75]);
});

test("handles empty peaks array", () => {
  assert.equal(liveWaveformColumns([]).length, 0);
  assert.equal(liveWaveformColumns(new Float32Array(0)).length, 0);
});

test("supports Float32Array inputs and options propagation", () => {
  const peaks = new Float32Array([0.2, 0.5]);
  const out = liveWaveformColumns(peaks, { mode: "half", scale: "linear", height: 50, gain: 1 });
  assert.equal(out.length, 4);
  assert.deepEqual([...out], [40, 50, 25, 50]);
});
