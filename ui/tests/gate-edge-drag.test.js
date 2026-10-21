// The owner reported (2026-10-21) that the borders of a clip inside an Auto-Silence stretch
// "cannot be dragged". These pin what the press logic sees there: the edge is hit and wins
// over the gate (timeline.js pointerdown starts an edge session whenever hitTest gives
// `clip` + `edge` on a track row, before the gate is looked at; dragIntent and tweakZone both
// stand back on an edge). The cause was visual: the gate's hatch was drawn over the whole
// clip, borders included, and the gate's own edge ticks looked like grab handles but are
// not (a gate boundary is not draggable). See docs/design/SILENCE-VISUALS.md.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { canStartClipDrag } from "../clip-drag.js";
import { dragIntent } from "../drag-mode.js";
import { EDGE_PX, hitTest, layoutFor, RULER_HEIGHT } from "../lanes.js";

// Zoom 10 frames per px: the clip spans x 100..200; the gate x 50..300 covers it whole.
const project = {
  rate: 48_000,
  buses: [],
  tracks: [
    {
      id: "t1",
      clips: [{ id: "c1", start: 1000, offset: 0, length: 1000, gain_db: 0, envelope: [] }],
      gate: [[500, 3000]],
    },
  ],
};
const view = { scroll: 0, zoom: 10, scrollY: 0, width: 800 };
const layout = layoutFor({ project, laneHeight: 80 });
const at = (x, y = RULER_HEIGHT + 40, extra = {}) =>
  hitTest({ layout, project, view: { ...view, ...extra }, x, y });

describe("dragging the border of a clip inside a closed stretch", () => {
  for (const [x, edge] of [
    [100, "start"],
    [200, "end"],
    [100 + EDGE_PX, "start"],
    [200 - EDGE_PX, "end"],
  ]) {
    test(`x ${x}: the ${edge} edge is hit, with the gate under it`, () => {
      const hit = at(x);
      assert.equal(hit.clip?.id, "c1");
      assert.equal(hit.edge, edge);
      assert.ok(hit.gate, "the gate is reported too");
      // What timeline.js pointerdown decides from this hit: an edge drag, nothing else.
      assert.equal(canStartClipDrag(hit), false, "not a move");
      assert.equal(
        dragIntent({ mode: "range", hit, rowY: 40 }),
        null,
        "not a range paint, in range mode",
      );
      assert.equal(dragIntent({ mode: "move", hit, rowY: 10 }), null, "nor in move mode");
    });
  }

  test("in the label strip too (where a press otherwise moves the clip)", () => {
    const hit = at(200, RULER_HEIGHT + 4);
    assert.equal(hit.edge, "end");
    assert.equal(canStartClipDrag(hit), false);
  });

  test("the same edge with gates hidden is hit the same way", () => {
    const hit = at(200, RULER_HEIGHT + 40, { showGates: false });
    assert.equal(hit.edge, "end");
    assert.equal(hit.gate, null);
  });

  test("a gate's own boundary away from any clip edge is not an edge", () => {
    const hit = at(300);
    assert.equal(hit.clip, null);
    assert.equal(hit.edge, null);
  });
});
