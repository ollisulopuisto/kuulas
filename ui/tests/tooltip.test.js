import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createRestDelay, REST_MS, tipPlacement } from "../tooltip.js";

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

describe("createRestDelay", () => {
  function setup() {
    const calls = [];
    let now = 0;
    let pending = null;
    const timers = {
      setTimeout: (fn, ms) => {
        pending = { fn, at: now + ms };
        return pending;
      },
      clearTimeout: (handle) => {
        if (pending === handle) pending = null;
      },
    };
    const rest = createRestDelay({
      onRest: () => calls.push("rest"),
      onMove: () => calls.push("move"),
      timers,
    });
    const advance = (ms) => {
      now += ms;
      if (pending && pending.at <= now) {
        const { fn } = pending;
        pending = null;
        fn();
      }
    };
    return { rest, calls, advance };
  }

  test("nothing shows before the pointer has rested for the full delay", () => {
    const { rest, calls, advance } = setup();
    rest.move(10, 10, "a");
    advance(REST_MS - 1);
    assert.deepEqual(calls, ["move"]);
    advance(1);
    assert.deepEqual(calls, ["move", "rest"]);
  });

  test("a move of more than a few pixels hides the hint and starts the wait again", () => {
    const { rest, calls, advance } = setup();
    rest.move(10, 10, "a");
    advance(REST_MS);
    rest.move(30, 10, "a");
    assert.deepEqual(calls, ["move", "rest", "move"]);
    advance(REST_MS - 1);
    assert.equal(calls.length, 3);
    advance(1);
    assert.equal(calls.at(-1), "rest");
  });

  test("jitter within a few pixels over the same text keeps the wait and the hint", () => {
    const { rest, calls, advance } = setup();
    rest.move(10, 10, "a");
    advance(300);
    rest.move(12, 11, "a");
    advance(300);
    assert.deepEqual(calls, ["move", "rest"]);
    rest.move(13, 12, "a");
    assert.deepEqual(calls, ["move", "rest"]);
  });

  test("new text under a still pointer starts the wait again", () => {
    const { rest, calls, advance } = setup();
    rest.move(10, 10, "a");
    advance(REST_MS);
    rest.move(10, 10, "b");
    assert.deepEqual(calls, ["move", "rest", "move"]);
  });

  test("cancel hides the hint and nothing shows later", () => {
    const { rest, calls, advance } = setup();
    rest.move(10, 10, "a");
    rest.cancel();
    advance(REST_MS * 2);
    assert.deepEqual(calls, ["move", "move"]);
  });
});
