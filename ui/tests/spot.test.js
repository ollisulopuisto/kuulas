import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { spotPlan } from "../spot.js";

describe("spot placement", () => {
  test("moves selected clips together so the earliest starts at the entered time", () => {
    const state = {
      selection: new Set(["a", "b"]),
      project: {
        tracks: [
          { id: "one", clips: [{ id: "a", start: 120, length: 50 }] },
          { id: "two", clips: [{ id: "b", start: 250, length: 50 }] },
        ],
      },
    };
    assert.deepEqual(spotPlan(state, 900), {
      kind: "edit",
      op: "shift_clips",
      args: { clip_ids: ["a", "b"], delta: 780 },
    });
  });

  test("moves the playhead when there is no selected clip", () => {
    assert.deepEqual(spotPlan({ selection: new Set(), project: { tracks: [] } }, 900), {
      kind: "playhead",
      frame: 900,
    });
  });

  test("spots every member of a selected clip group", () => {
    const state = {
      selection: new Set(["a"]),
      project: {
        tracks: [
          { id: "one", clips: [{ id: "a", start: 120, length: 50, group: "g" }] },
          { id: "two", clips: [{ id: "b", start: 250, length: 50, group: "g" }] },
        ],
      },
    };
    assert.deepEqual(spotPlan(state, 900), {
      kind: "edit",
      op: "shift_clips",
      args: { clip_ids: ["a", "b"], delta: 780 },
    });
  });
});
