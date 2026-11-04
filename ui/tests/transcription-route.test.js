import assert from "node:assert/strict";
import test from "node:test";
import { transcriptionBackendForMemory } from "../transcription-route.js";

test("local transcription stays local when the machine meets the memory requirement", () => {
  assert.equal(transcriptionBackendForMemory({ eligible: true }), "local");
});

test("local transcription routes to Colab when the machine is below the memory requirement", () => {
  assert.equal(transcriptionBackendForMemory({ eligible: false }), "colab");
});

test("unknown memory eligibility fails closed to Colab", () => {
  assert.equal(transcriptionBackendForMemory(null), "colab");
  assert.equal(transcriptionBackendForMemory({}), "colab");
});
