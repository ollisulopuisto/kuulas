import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  GRACE_DELAY,
  HOVER_DELAY,
  isHoverPointer,
  movingToward,
  rowHover,
  topHover,
} from "../menu-hover.js";

describe("which pointers hover", () => {
  test("only a mouse does; touch and pen do nothing special", () => {
    assert.equal(isHoverPointer("mouse"), true);
    assert.equal(isHoverPointer("touch"), false);
    assert.equal(isHoverPointer("pen"), false);
    assert.equal(isHoverPointer(undefined), false);
  });
});

describe("top-level titles", () => {
  test("another title opens at once while a menu is open", () => {
    assert.equal(topHover({ open: true, top: 0, target: 2 }), "open");
  });
  test("never opens a closed bar", () => {
    assert.equal(topHover({ open: false, top: 0, target: 2 }), "none");
  });
  test("the title that is already open does nothing", () => {
    assert.equal(topHover({ open: true, top: 2, target: 2 }), "none");
  });
});

describe("rows in a list", () => {
  const base = { subOpen: false, openRow: -1, towardSub: false };
  test("a submenu row opens its submenu after the delay", () => {
    assert.deepEqual(rowHover({ ...base, row: 3, rowIsSubmenu: true }), {
      act: "open-sub",
      delay: HOVER_DELAY,
    });
    assert.equal(HOVER_DELAY, 90);
  });
  test("resting on the row whose submenu is open keeps it", () => {
    assert.deepEqual(rowHover({ ...base, subOpen: true, openRow: 3, row: 3, rowIsSubmenu: true }), {
      act: "cancel",
    });
  });
  test("another submenu row switches after the delay", () => {
    assert.deepEqual(rowHover({ ...base, subOpen: true, openRow: 3, row: 5, rowIsSubmenu: true }), {
      act: "open-sub",
      delay: HOVER_DELAY,
    });
  });
  test("a plain row closes the open submenu at once", () => {
    assert.deepEqual(
      rowHover({ ...base, subOpen: true, openRow: 3, row: 4, rowIsSubmenu: false }),
      { act: "close-sub", delay: 0 },
    );
  });
  test("a plain row with nothing open does nothing", () => {
    assert.deepEqual(rowHover({ ...base, row: 4, rowIsSubmenu: false }), { act: "cancel" });
  });
  test("travelling toward the open submenu only delays the close", () => {
    assert.deepEqual(
      rowHover({
        ...base,
        subOpen: true,
        openRow: 3,
        row: 4,
        rowIsSubmenu: false,
        towardSub: true,
      }),
      { act: "close-sub", delay: GRACE_DELAY },
    );
    // The open is quick, the grace for a wobbly diagonal stays generous.
    assert.ok(HOVER_DELAY < GRACE_DELAY);
  });
});

describe("diagonal grace", () => {
  const sub = { left: 100, right: 200, top: 0, bottom: 100 };
  test("a move toward the submenu's near edge counts", () => {
    assert.equal(movingToward({ x: 50, y: 10 }, { x: 70, y: 30 }, sub), true);
  });
  test("a move straight down, away from it, does not", () => {
    assert.equal(movingToward({ x: 50, y: 10 }, { x: 50, y: 60 }, sub), false);
  });
  test("a move left does not", () => {
    assert.equal(movingToward({ x: 50, y: 10 }, { x: 20, y: 12 }, sub), false);
  });
  test("a submenu opening to the left uses its right edge", () => {
    assert.equal(movingToward({ x: 250, y: 10 }, { x: 230, y: 30 }, sub), true);
  });
  test("no previous position or no rectangle: no grace", () => {
    assert.equal(movingToward(null, { x: 1, y: 1 }, sub), false);
    assert.equal(movingToward({ x: 1, y: 1 }, { x: 2, y: 2 }, null), false);
  });
});
