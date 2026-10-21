import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { drawGateHatch, drawPreviewBands } from "../paint.js";

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

const COLOURS = { fill: "rgb(0 0 1 / 0.2)", edge: "#0a0" };

describe("Auto-Silence preview bands: unlike a committed gate, not by colour alone", () => {
  test("a veil, a hatch the other way and dashed edges for each run", () => {
    const { ctx, ops } = recorder();
    drawPreviewBands(ctx, [10, 60, 100, 130], 20, 40, COLOURS);
    const fills = ops.filter((op) => op[0] === "fillRect");
    assert.deepEqual(fills, [
      ["fillRect", 10, 20, 50, 40],
      ["fillRect", 100, 20, 30, 40],
    ]);
    assert.ok(ops.some((op) => op[0] === "setLineDash" && op[1].length > 0));
    assert.ok(ops.some((op) => op[0] === "set" && op[1] === "fillStyle" && op[2] === COLOURS.fill));
    assert.ok(
      ops.some((op) => op[0] === "set" && op[1] === "strokeStyle" && op[2] === COLOURS.edge),
    );
    // The hatch runs from top-left to bottom-right: a committed gate's runs the other way.
    const moves = ops.filter((op) => op[0] === "moveTo" || op[0] === "lineTo");
    const firstLine = moves.findIndex((op) => op[0] === "moveTo" && op[2] === 20);
    assert.ok(firstLine >= 0);
    assert.equal(moves[firstLine + 1][0], "lineTo");
    assert.equal(moves[firstLine + 1][2], 60);
    assert.ok(moves[firstLine + 1][1] > moves[firstLine][1]);
  });

  test("it does not draw what a committed gate draws", () => {
    const preview = recorder();
    drawPreviewBands(preview.ctx, [10, 60], 20, 40, COLOURS);
    const gate = recorder();
    drawGateHatch(gate.ctx, [10, 60], 20, 40, COLOURS.edge);
    assert.notDeepEqual(preview.ops, gate.ops);
  });

  test("no runs, nothing drawn", () => {
    const { ctx, ops } = recorder();
    drawPreviewBands(ctx, [], 0, 10, COLOURS);
    assert.deepEqual(ops, []);
  });
});
