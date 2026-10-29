import assert from "node:assert/strict";
import { test } from "node:test";
import { partRange } from "../part-versions-model.js";

const project = {
  tracks: [
    {
      id: "t",
      clips: [
        { id: "a", start: 10, length: 20 },
        { id: "b", start: 40, length: 10 },
      ],
    },
    { id: "other", clips: [{ id: "c", start: 0, length: 100 }] },
  ],
};

test("marked range uses focused track, with reversed marks supported", () => {
  assert.deepEqual(partRange({ project, focusTrack: "t", inPoint: 80, outPoint: 20 }), {
    track_id: "t",
    start: 20,
    end: 80,
  });
});
test("selected clips on one track supply range and track", () => {
  assert.deepEqual(partRange({ project, selection: new Set(["a", "b"]) }), {
    track_id: "t",
    start: 10,
    end: 50,
  });
});
test("selection across tracks and missing range do not guess", () => {
  assert.equal(partRange({ project, selection: new Set(["a", "c"]) }), null);
  assert.equal(partRange({ project, focusTrack: "t" }), null);
});
