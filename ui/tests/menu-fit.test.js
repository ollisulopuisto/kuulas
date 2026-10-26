import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { placeMenu } from "../menu-fit.js";

const view = { width: 1000, height: 800 };

describe("placeMenu", () => {
  test("a submenu that runs past the right edge opens to the left of its parent", () => {
    const box = { left: 900, top: 100, width: 200, height: 100 };
    assert.equal(placeMenu({ box, parent: { left: 700 }, view }).flipX, true);
  });

  test("a submenu that fits stays to the right", () => {
    const box = { left: 720, top: 100, width: 200, height: 100 };
    assert.equal(placeMenu({ box, parent: { left: 500 }, view }).flipX, false);
  });

  test("a submenu does not flip when the left side has no room either", () => {
    const box = { left: 900, top: 100, width: 200, height: 100 };
    assert.equal(placeMenu({ box, parent: { left: 150 }, view }).flipX, false);
  });

  test("a top-level list never flips", () => {
    const box = { left: 900, top: 100, width: 200, height: 100 };
    assert.equal(placeMenu({ box, view }).flipX, false);
  });

  test("a list past the bottom moves up until its bottom meets the margin", () => {
    const box = { left: 0, top: 700, width: 200, height: 300 };
    assert.equal(placeMenu({ box, view }).shiftY, -208);
  });

  test("a list taller than the window moves up only to the top margin", () => {
    const box = { left: 0, top: 100, width: 200, height: 900 };
    assert.equal(placeMenu({ box, view }).shiftY, -92);
  });

  test("a list that fits does not move", () => {
    const box = { left: 0, top: 100, width: 200, height: 300 };
    assert.equal(placeMenu({ box, view }).shiftY, 0);
  });
});
