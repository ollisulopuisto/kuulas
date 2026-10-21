// "Open the muted stretches under the selected clips": when it applies (owner, 21.10.2026:
// a gate is a track property, but it must be possible to unset it per clip or for several).
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { gateUnderClips } from "../gate.js";
import { timelineMenuItems, timelineTarget } from "../timeline-menu.js";

const project = {
  tracks: [
    {
      id: "a",
      gate: [[100, 200]],
      clips: [
        { id: "c1", start: 0, length: 90 },
        { id: "c2", start: 150, length: 100 },
      ],
    },
    { id: "b", gate: [], clips: [{ id: "c3", start: 0, length: 500 }] },
  ],
};

describe("gateUnderClips", () => {
  test("a selected clip over a closed stretch", () => {
    assert.equal(gateUnderClips(project, new Set(["c2"])), true);
  });
  test("a selected clip clear of the gate", () => {
    assert.equal(gateUnderClips(project, new Set(["c1"])), false);
  });
  test("a clip on a track without a gate", () => {
    assert.equal(gateUnderClips(project, new Set(["c3"])), false);
  });
  test("nothing selected, or arrays and junk", () => {
    assert.equal(gateUnderClips(project, new Set()), false);
    assert.equal(gateUnderClips(project, ["c2"]), true);
    assert.equal(gateUnderClips(null, null), false);
  });
});

describe("the context menus offer it", () => {
  const state = { project, selection: new Set(["c2"]), inPoint: null, outPoint: null };
  const ids = (target, can) =>
    timelineMenuItems(state, target, can).flatMap((s) => s.items.map((i) => i.id));
  test("on a clip, when the selection has a closed stretch under it", () => {
    assert.ok(ids({ kind: "clip" }, () => true).includes("gate.open_under_clips"));
    assert.ok(
      !ids({ kind: "clip" }, (id) => id !== "gate.open_under_clips").includes(
        "gate.open_under_clips",
      ),
    );
  });
  test("on a closed stretch the stretch itself can be opened", () => {
    const hit = {
      area: "lane",
      frame: 120,
      clip: null,
      row: { kind: "track", id: "a" },
      gate: { trackId: "a", range: [100, 200] },
    };
    const target = timelineTarget(hit, state);
    assert.equal(target.gate, true);
    assert.ok(ids(target, () => true).includes("gate.open_stretch"));
    assert.ok(!ids({ kind: "lane", gate: false }, () => true).includes("gate.open_stretch"));
  });
});
