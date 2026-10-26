import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { tipPlacement } from "../tooltip.js";

const view = { width: 1000, height: 800 };

describe("tipPlacement", () => {
  test("a tip sits just below and to the right of the pointer", () => {
    assert.deepEqual(tipPlacement({ x: 100, y: 100 }, { width: 200, height: 40 }, view), {
      left: 114,
      top: 118,
    });
  });

  test("a tip near the right edge opens to the left of the pointer", () => {
    const at = tipPlacement({ x: 950, y: 100 }, { width: 200, height: 40 }, view);
    assert.equal(at.left, 950 - 200 - 14);
  });

  test("a tip near the bottom edge opens above the pointer", () => {
    const at = tipPlacement({ x: 100, y: 790 }, { width: 200, height: 40 }, view);
    assert.equal(at.top, 790 - 40 - 10);
  });

  test("a tip never leaves the window", () => {
    const at = tipPlacement({ x: 0, y: 0 }, { width: 2000, height: 40 }, view);
    assert.ok(at.left >= 8 && at.top >= 8);
  });
});
