import assert from "node:assert/strict";
import { test } from "node:test";
import { focusHeights } from "../focus-layout.js";
import { fitHeight } from "../lane-sizing.js";
import { layoutFor } from "../lanes.js";

for (const folded of [false, true]) {
  test(`single-member bus fitting includes its strip (folded=${folded})`, () => {
    const project = {
      buses: [{ id: "bus" }],
      tracks: [
        { id: "a", bus: "bus" },
        { id: "b", bus: null },
      ],
    };
    const collapsed = new Set(folded ? ["bus"] : []);
    const options = { project, available: 300, busHeight: 56, groupGap: 14, collapsed };
    const laneHeight = fitHeight(options);
    const state = { ...options, laneHeight, collapsedBuses: collapsed };
    assert.ok(layoutFor(state).height <= 300);
    const heights = focusHeights({ ...options, focusIds: ["b"] });
    assert.ok(layoutFor({ ...state, focusHeights: heights }).height <= 300);
  });
}
