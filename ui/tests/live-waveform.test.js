import assert from "node:assert/strict";
import { test } from "node:test";
import { liveWaveformColumns } from "../live-take.js";

test("live waveforms obey the same half/full display as finished clips", () => {
  assert.deepEqual([...liveWaveformColumns([0.5], { mode: "half", height: 100 })], [50, 100]);
  assert.deepEqual([...liveWaveformColumns([0.5], { mode: "full", height: 100 })], [25, 75]);
});
