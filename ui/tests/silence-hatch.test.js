import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { drawGateHatch, drawSilenceHatch, HATCH_STEP } from "../paint.js";

function recorder() {
  const ops = [];
  const ctx = new Proxy(
    {},
    {
      get:
        (_target, name) =>
        (...args) =>
          ops.push([name, ...args]),
      set: (_target, name, value) => {
        ops.push(["set", name, value]);
        return true;
      },
    },
  );
  return { ctx, ops };
}

describe("silence hatch: muted clip and Auto-Silence gate look the same", () => {
  test("a gate run draws exactly what a muted clip of the same box draws", () => {
    const clip = recorder();
    drawSilenceHatch(clip.ctx, 10, 22, 50, 40, "#123456");
    const gate = recorder();
    drawGateHatch(gate.ctx, [10, 60], 22, 40, "#123456");
    assert.ok(clip.ops.length > 5);
    assert.deepEqual(gate.ops, clip.ops);
  });

  test("each gate run is hatched on its own, with the shared line step", () => {
    const gate = recorder();
    drawGateHatch(gate.ctx, [0, 12, 100, 130], 0, 10, "#fff");
    assert.equal(gate.ops.filter((op) => op[0] === "stroke").length, 2);
    const first = gate.ops.filter((op) => op[0] === "moveTo");
    assert.equal(first[1][1] - first[0][1], HATCH_STEP);
  });
});
