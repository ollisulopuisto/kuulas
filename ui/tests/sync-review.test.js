import assert from "node:assert/strict";
import { test } from "node:test";
import { auditionRange, moveRequest, selectedTrackIds } from "../sync-review-model.js";

const project = {
  rate: 48000,
  tracks: [
    { id: "a", clips: [{ id: "a1", start: 0, length: 48000 }] },
    {
      id: "b",
      clips: [
        { id: "b1", start: 48000, length: 48000 },
        { id: "b2", start: 144000, length: 48000 },
      ],
    },
  ],
};

test("selection expands participant tracks, not only selected pieces", () => {
  assert.deepEqual(selectedTrackIds({ project, selection: new Set(["b1", "a1"]) }), ["a", "b"]);
  assert.deepEqual(selectedTrackIds({ project, trackSelection: new Set(["b", "a"]) }), ["a", "b"]);
});
test("whole track uses relative shift, explicit piece uses absolute total", () => {
  const review = { id: "r", offsets: { b1: 100, b2: 100 } };
  assert.deepEqual(moveRequest(review, "b", "b1", 50, "track"), {
    id: "r",
    track: "b",
    frames: 50,
    clip: null,
  });
  assert.deepEqual(moveRequest(review, "b", "b1", 50, "clip"), {
    id: "r",
    track: "b",
    frames: 150,
    clip: "b1",
  });
});
test("audition stays around selected handoff and in recorded duration", () => {
  assert.deepEqual(auditionRange(48000 * 2, 48000 * 20, 48000), { at: 0, seconds: 6 });
  assert.deepEqual(auditionRange(48000 * 19, 48000 * 20, 48000), { at: 48000 * 16, seconds: 4 });
});

test("manual changes are not still labeled as the computed suggestion", async () => {
  const { timingStatus } = await import("../sync-review-model.js");
  const track = { clips: [{ id: "a" }, { id: "b" }] };
  assert.equal(
    timingStatus({ offsets: { a: 20, b: 20 }, suggestion: { a: 20, b: 20 } }, track, {
      status: "proposal",
    }),
    "proposal",
  );
  assert.equal(
    timingStatus({ offsets: { a: 20, b: 21 }, suggestion: { a: 20, b: 20 } }, track, {
      status: "proposal",
    }),
    "manual",
  );
});

test("a single explicit track is not silently widened to every participant", () => {
  assert.deepEqual(selectedTrackIds({ project, trackSelection: new Set(["b"]) }), ["b"]);
});
