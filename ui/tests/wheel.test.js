import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  classifyWheel,
  DEFAULT_WHEEL_MODE,
  gestureZoom,
  nextWheelMode,
  wheelIntent,
  wheelModeChoice,
} from "../wheel.js";

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
    const out = wheelIntent(wheel({ deltaX: 12, deltaY: 5.5 }), {
      lanesFit: true,
      mode: "scroll",
    });
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

describe("two-finger scroll preference", () => {
  const zoomMode = { lanesFit: false, mode: "zoom" };
  const scrollMode = { lanesFit: false, mode: "scroll" };

  test("the default is zoom, and stored junk falls back to it", () => {
    assert.equal(DEFAULT_WHEEL_MODE, "zoom");
    assert.equal(wheelModeChoice(null), "zoom");
    assert.equal(wheelModeChoice("bogus"), "zoom");
    assert.equal(wheelModeChoice("scroll"), "scroll");
    assert.equal(nextWheelMode("zoom"), "scroll");
    assert.equal(nextWheelMode("scroll"), "zoom");
  });

  test("a missing mode means zoom", () => {
    const out = wheelIntent(wheel({ deltaY: 5.5 }), { lanesFit: false });
    assert.equal(out.kind, "zoom");
  });

  test("zoom mode: vertical trackpad movement zooms like Cmd + wheel, same sign", () => {
    for (const lanesFit of [true, false]) {
      for (const deltaY of [-7.5, 7.5]) {
        const out = wheelIntent(wheel({ deltaY }), { lanesFit, mode: "zoom" });
        const cmd = wheelIntent(wheel({ deltaY, metaKey: true }), { lanesFit, mode: "zoom" });
        assert.deepEqual(out, cmd);
      }
    }
    assert.ok(wheelIntent(wheel({ deltaY: -7.5 }), zoomMode).factor < 1);
    assert.ok(wheelIntent(wheel({ deltaY: 7.5 }), zoomMode).factor > 1);
  });

  test("zoom mode: horizontal movement scrolls time only", () => {
    assert.deepEqual(wheelIntent(wheel({ deltaX: 12.5 }), zoomMode), {
      kind: "scroll",
      dx: 12.5,
      dy: 0,
    });
  });

  test("zoom mode: a diagonal swipe goes by the dominant axis", () => {
    assert.deepEqual(wheelIntent(wheel({ deltaX: 12.5, deltaY: 3.5 }), zoomMode), {
      kind: "scroll",
      dx: 12.5,
      dy: 0,
    });
    assert.equal(wheelIntent(wheel({ deltaX: 3.5, deltaY: 12.5 }), zoomMode).kind, "zoom");
  });

  test("zoom mode: Shift + vertical scrolls the lanes", () => {
    for (const lanesFit of [true, false]) {
      assert.deepEqual(
        wheelIntent(wheel({ deltaY: 9.5, shiftKey: true }), { lanesFit, mode: "zoom" }),
        {
          kind: "scroll",
          dx: 0,
          dy: 9.5,
        },
      );
    }
  });

  test("zoom mode: Shift + horizontal (axis swapped by the OS) still scrolls time", () => {
    assert.deepEqual(wheelIntent(wheel({ deltaX: 9.5, shiftKey: true }), zoomMode), {
      kind: "scroll",
      dx: 9.5,
      dy: 0,
    });
  });

  test("scroll mode keeps today's trackpad behaviour", () => {
    assert.deepEqual(wheelIntent(wheel({ deltaX: 12, deltaY: 5.5 }), scrollMode), {
      kind: "scroll",
      dx: 12,
      dy: 5.5,
    });
    assert.deepEqual(wheelIntent(wheel({ deltaY: 5.5, shiftKey: true }), scrollMode), {
      kind: "scroll",
      dx: 5.5,
      dy: 0,
    });
  });

  test("a notched mouse wheel is the same in both modes", () => {
    for (const mode of ["zoom", "scroll"]) {
      assert.deepEqual(wheelIntent(wheel({ deltaY: 100 }), { lanesFit: false, mode }), {
        kind: "scroll",
        dx: 0,
        dy: 100,
      });
      assert.deepEqual(wheelIntent(wheel({ deltaY: 100 }), { lanesFit: true, mode }), {
        kind: "scroll",
        dx: 100,
        dy: 0,
      });
      assert.equal(
        wheelIntent(wheel({ deltaY: 3, deltaMode: 1 }), { lanesFit: false, mode }).dy,
        48,
      );
      assert.equal(
        wheelIntent(wheel({ deltaY: 100, metaKey: true }), { lanesFit: false, mode }).kind,
        "zoom",
      );
    }
  });

  test("Mod zooms and Alt changes the waveform in both modes", () => {
    for (const mode of ["zoom", "scroll"]) {
      for (const key of ["ctrlKey", "metaKey"]) {
        const out = wheelIntent(wheel({ deltaX: 3, deltaY: -10, [key]: true }), {
          lanesFit: true,
          mode,
        });
        assert.equal(out.kind, "zoom");
        assert.ok(out.factor < 1);
      }
      assert.equal(
        wheelIntent(wheel({ deltaY: -10, altKey: true }), { lanesFit: true, mode }).kind,
        "waveform",
      );
    }
  });
});

describe("gestureZoom", () => {
  test("a growing scale zooms in, a shrinking one zooms out", () => {
    assert.ok(gestureZoom(1, 1.5).factor < 1);
    assert.equal(gestureZoom(1, 1.5).kind, "zoom");
    assert.ok(gestureZoom(1.5, 1).factor > 1);
  });

  test("equal scales give factor 1", () => {
    assert.deepEqual(gestureZoom(2, 2), { kind: "zoom", factor: 1 });
  });

  test("scale of 0, a missing value, or a non-finite value returns null", () => {
    assert.equal(gestureZoom(1, 0), null);
    assert.equal(gestureZoom(1, undefined), null);
    assert.equal(gestureZoom(undefined, 2), null);
    assert.equal(gestureZoom(1, NaN), null);
    assert.equal(gestureZoom(1, Infinity), null);
    assert.equal(gestureZoom(NaN, 2), null);
    assert.equal(gestureZoom(1, null), null);
  });
});
