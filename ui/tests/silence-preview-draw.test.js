import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { drawPreviewBands } from "../paint.js";

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

const COLOURS = { edge: "#0a0" };

// docs/design/SILENCE-VISUALS.md: the preview is the teal outline of the would-close wave
// (drawn by the waveform layer) plus these dashed edges. No veil, no hatch: nothing is hatched.
describe("Auto-Silence preview bands: dashed edges only", () => {
  test("dashed top and bottom edges per run, inside the body, in the preview colour", () => {
    const { ctx, ops } = recorder();
    drawPreviewBands(ctx, [10, 60, 100, 130], 20, 40, COLOURS);
    assert.ok(ops.some((op) => op[0] === "setLineDash" && op[1].length > 0));
    assert.ok(ops.some((op) => op[0] === "set" && op[1] === "strokeStyle" && op[2] === "#0a0"));
    const moves = ops.filter((op) => op[0] === "moveTo");
    assert.deepEqual(
      moves.map((op) => op.slice(1)),
      [
        [10, 22.5],
        [10, 57.5],
        [100, 22.5],
        [100, 57.5],
      ],
      "2 px inside the body: the clip border, drawn above, does not hide them",
    );
  });

  test("no veil and no hatch", () => {
    const { ctx, ops } = recorder();
    drawPreviewBands(ctx, [10, 60], 20, 40, COLOURS);
    assert.equal(ops.filter((op) => op[0] === "fillRect").length, 0);
    assert.equal(ops.filter((op) => op[0] === "lineTo").length, 2, "two edges, no hatch lines");
  });

  test("no runs, nothing drawn", () => {
    const { ctx, ops } = recorder();
    drawPreviewBands(ctx, [], 0, 10, COLOURS);
    assert.deepEqual(ops, []);
  });
});
