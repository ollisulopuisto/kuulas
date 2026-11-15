import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { drawPlayhead } from "../playhead-render.js";

function context() {
  const calls = [];
  return {
    calls,
    setTransform: (...args) => calls.push(["setTransform", ...args]),
    clearRect: (...args) => calls.push(["clearRect", ...args]),
    beginPath: () => calls.push(["beginPath"]),
    moveTo: (...args) => calls.push(["moveTo", ...args]),
    lineTo: (...args) => calls.push(["lineTo", ...args]),
    stroke: () => calls.push(["stroke"]),
    closePath: () => calls.push(["closePath"]),
    fill: () => calls.push(["fill"]),
  };
}

describe("the independent playhead layer", () => {
  test("draws fractional pixel positions without snapping to whole CSS pixels", () => {
    const ctx = context();
    drawPlayhead(ctx, {
      frame: 121.25,
      scroll: 0,
      zoom: 10,
      width: 100,
      height: 200,
      ratio: 2,
      color: "red",
    });
    assert.ok(ctx.calls.some((call) => call[0] === "moveTo" && call[1] === 12.125));
    assert.ok(ctx.calls.some((call) => call[0] === "lineTo" && call[1] === 12.125));
    assert.ok(ctx.calls.some((call) => call[0] === "clearRect"));
  });

  test("clears stale pixels when the playhead leaves the visible area", () => {
    const ctx = context();
    const drawn = drawPlayhead(ctx, {
      frame: 1000,
      scroll: 0,
      zoom: 1,
      width: 100,
      height: 200,
      color: "red",
    });
    assert.equal(drawn, false);
    assert.ok(ctx.calls.some((call) => call[0] === "clearRect"));
    assert.ok(!ctx.calls.some((call) => call[0] === "stroke"));
  });
});
