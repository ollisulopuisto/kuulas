import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dispatchTranscription, transcriptionBackendForMemory } from "../transcription-route.js";

const appSource = readFileSync(fileURLToPath(new URL("../app.js", import.meta.url)), "utf8");

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

test("bulk local transcription uses Colab when local memory is insufficient", async () => {
  const calls = [];
  await dispatchTranscription({
    ids: ["recording-1", "recording-2"],
    backend: "local",
    getLocalStatus: async () => ({ eligible: false }),
    transcribeLocal: (ids) => calls.push(["local", ids]),
    transcribeColab: (ids) => calls.push(["colab", ids]),
  });
  assert.deepEqual(calls, [["colab", ["recording-1", "recording-2"]]]);
});

test("explicit Colab transcription skips the local memory check", async () => {
  const calls = [];
  await dispatchTranscription({
    ids: ["recording-1"],
    backend: "colab",
    getLocalStatus: async () => calls.push(["memory-check"]),
    transcribeLocal: (ids) => calls.push(["local", ids]),
    transcribeColab: (ids) => calls.push(["colab", ids]),
  });
  assert.deepEqual(calls, [["colab", ["recording-1"]]]);
});

test("bulk transcription uses transcript flow and routes local requests through the guard", () => {
  const start = appSource.indexOf("async function transcribeAll(");
  const end = appSource.indexOf("// Transcription is a background job", start);
  assert.notEqual(start, -1);
  assert.match(
    appSource.slice(start, end),
    /transcript\.transcribe\(ids, \{ backend, localEngine \}\)/,
  );
  assert.match(appSource, /transcribeLocal: \(ids, options\) => transcribeLocalOrColab\(ids, options\)/);
});
