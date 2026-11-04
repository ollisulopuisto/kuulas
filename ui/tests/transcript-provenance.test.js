import assert from "node:assert/strict";
import { test } from "node:test";
import { provenanceLabel, rerunOptions } from "../transcript-provenance.js";

test("provenance label identifies backend, model, language, and creation time", () => {
  assert.equal(
    provenanceLabel(
      { backend: "local", tool: "whisper", model: "large-v3-turbo", language: "fi" },
      "2026-11-04T08:15:00Z",
      (key, values = {}) => {
        if (key === "ui.transcript.backend.local") return "Local";
        if (key === "ui.transcript.tool.whisper") return "Whisper";
        return `${key}:${Object.values(values).join("|")}`;
      },
      (value) => `date:${value}`,
    ),
    "ui.transcript.provenance:Local|Whisper|large-v3-turbo|fi|date:2026-11-04T08:15:00Z",
  );
});

test("rerun repeats known settings and falls back safely for imported transcripts", () => {
  assert.deepEqual(
    rerunOptions({ backend: "colab", tool: "whisper", model: "large-v3", language: "fi" }),
    { backend: "colab", model: "large-v3", language: "fi", localEngine: "whisper" },
  );
  assert.deepEqual(rerunOptions({ tool: "nhsx" }), {
    backend: "local", model: undefined, language: undefined, localEngine: "whisper",
  });
});

test("rerunning an Orukeet transcript keeps the local engine", () => {
  assert.deepEqual(rerunOptions({ backend: "local", tool: "orukeet", model: "small" }), {
    backend: "local", model: "small", language: undefined, localEngine: "orukeet",
  });
});
