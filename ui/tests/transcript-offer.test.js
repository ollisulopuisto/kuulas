// The transcript dock's "Transcription missing" list: one row per untranscribed recording.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { offerRows } from "../transcript-offer.js";

const media = [
  { id: "a", name: "Anna.wav" },
  { id: "b", name: "Ben.wav" },
  { id: "c", name: "Cleo.wav" },
];
const job = (extra) => ({ kind: "transcribe", state: "running", progress: 0.4, ...extra });

describe("offerRows", () => {
  test("every untranscribed recording gets a row, with an All row for two or more", () => {
    const { rows, all } = offerRows({ media, transcribed: ["b"], jobs: [] });
    assert.deepEqual(
      rows.map((row) => [row.id, row.status]),
      [
        ["a", "none"],
        ["c", "none"],
      ],
    );
    assert.deepEqual(all, ["a", "c"]);
  });

  test("a single missing recording has no All row", () => {
    const { rows, all } = offerRows({ media, transcribed: ["a", "b"], jobs: [] });
    assert.equal(rows.length, 1);
    assert.equal(all, null);
  });

  test("nothing missing: no rows", () => {
    assert.deepEqual(offerRows({ media, transcribed: ["a", "b", "c"], jobs: [] }), {
      rows: [],
      all: null,
    });
  });

  test("a running or queued job for a recording replaces its buttons by progress", () => {
    const jobs = [
      job({ media: ["a"], backend: "colab" }),
      job({ media: ["b", "c"], state: "queued", progress: 0 }),
    ];
    const { rows, all } = offerRows({ media, transcribed: [], jobs });
    assert.deepEqual(
      rows.map((row) => [row.id, row.status, row.progress]),
      [
        ["a", "running", 0.4],
        ["b", "queued", 0],
        ["c", "queued", 0],
      ],
    );
    assert.equal(rows[0].backend, "colab");
    assert.equal(all, null);
  });

  test("All covers only the recordings with no job", () => {
    const { all } = offerRows({ media, transcribed: [], jobs: [job({ media: ["a"] })] });
    assert.deepEqual(all, ["b", "c"]);
  });

  test("a failed job keeps the buttons and carries its error", () => {
    const jobs = [job({ media: ["a"], state: "failed", error: { text: "no GPU" } })];
    const { rows } = offerRows({ media, transcribed: ["b", "c"], jobs });
    assert.equal(rows[0].status, "failed");
    assert.equal(rows[0].error, "no GPU");
  });

  test("finished and unrelated jobs are ignored", () => {
    const jobs = [
      job({ media: ["a"], state: "completed" }),
      { kind: "export", state: "running", progress: 0.5 },
      job({ media: undefined }),
    ];
    const { rows } = offerRows({ media, transcribed: ["b", "c"], jobs });
    assert.equal(rows[0].status, "none");
  });

  test("a running job wins over an older failed one", () => {
    const jobs = [
      job({ media: ["a"], state: "failed", error: { text: "x" } }),
      job({ media: ["a"], state: "running" }),
    ];
    assert.equal(offerRows({ media, transcribed: ["b", "c"], jobs }).rows[0].status, "running");
  });
});

test("active rows retain job identity and waiting message for cancel", () => {
  const { rows } = offerRows({
    media,
    transcribed: [],
    jobs: [job({ id: "local-2", state: "queued", media: ["b"], message: "waiting" })],
  });
  assert.equal(rows[1].jobId, "local-2");
  assert.equal(rows[1].message, "waiting");
});
