import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { classifyWheel, wheelIntent } from "../wheel.js";

const wheel = (over) => ({
  deltaX: 0,
  deltaY: 0,
  deltaMode: 0,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...over,
});

describe("wheel and trackpad", () => {
  test("a notched mouse wheel and a trackpad are told apart", () => {
    assert.equal(classifyWheel(wheel({ deltaY: 100 })), "mouse");
    assert.equal(classifyWheel(wheel({ deltaY: 3, deltaMode: 1 })), "mouse");
    assert.equal(classifyWheel(wheel({ deltaY: 3.5, deltaX: 2 })), "trackpad");
    assert.equal(classifyWheel(wheel({ deltaY: 7 })), "trackpad");
  });

  test("a trackpad scrolls naturally in both directions", () => {
    const out = wheelIntent(wheel({ deltaX: 12, deltaY: 5.5 }), { lanesFit: true });
    assert.deepEqual(out, { kind: "scroll", dx: 12, dy: 5.5 });
  });

  test("a mouse wheel scrolls time when all lanes fit, lanes otherwise", () => {
    assert.deepEqual(wheelIntent(wheel({ deltaY: 100 }), { lanesFit: true }), {
      kind: "scroll",
      dx: 100,
      dy: 0,
    });
    assert.deepEqual(wheelIntent(wheel({ deltaY: 100 }), { lanesFit: false }), {
      kind: "scroll",
      dx: 0,
      dy: 100,
    });
  });

  test("Shift + wheel always scrolls time, also when the OS swapped the axis", () => {
    for (const lanesFit of [true, false]) {
      assert.deepEqual(wheelIntent(wheel({ deltaY: 100, shiftKey: true }), { lanesFit }), {
        kind: "scroll",
        dx: 100,
        dy: 0,
      });
      assert.deepEqual(wheelIntent(wheel({ deltaX: 100, shiftKey: true }), { lanesFit }), {
        kind: "scroll",
        dx: 100,
        dy: 0,
      });
    }
  });

  test("line-based wheels are scaled to pixels", () => {
    const out = wheelIntent(wheel({ deltaY: 3, deltaMode: 1 }), { lanesFit: false });
    assert.deepEqual(out, { kind: "scroll", dx: 0, dy: 48 });
  });

  test("Mod + wheel and pinch zoom continuously, wheel up zooms in", () => {
    for (const key of ["ctrlKey", "metaKey"]) {
      const closer = wheelIntent(wheel({ deltaY: -10, [key]: true }), { lanesFit: true });
      assert.equal(closer.kind, "zoom");
      assert.ok(closer.factor < 1);
      const wider = wheelIntent(wheel({ deltaY: 10, [key]: true }), { lanesFit: true });
      assert.ok(wider.factor > 1);
    }
  });

  test("Alt + wheel changes the waveform height, not the zoom", () => {
    const up = wheelIntent(wheel({ deltaY: -100, altKey: true }), { lanesFit: true });
    assert.equal(up.kind, "waveform");
    assert.ok(up.factor > 1);
    assert.ok(wheelIntent(wheel({ deltaY: 100, altKey: true }), { lanesFit: true }).factor < 1);
  });
});
