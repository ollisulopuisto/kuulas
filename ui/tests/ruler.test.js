import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { rulerTicks } from "../ruler.js";

const RATE = 48_000;

describe("ruler ticks", () => {
  test("labels sit at least 80 px apart at any zoom", () => {
    for (const secondsOnScreen of [0.1, 1, 2, 30, 600, 7200]) {
      const zoom = (secondsOnScreen * RATE) / 1000;
      const ticks = rulerTicks({ scroll: 0, zoom, width: 1000, rate: RATE });
      const major = ticks.filter((t) => t.label !== null);
      assert.ok(major.length >= 2, `${secondsOnScreen}s: ${major.length}`);
      for (let i = 1; i < major.length; i += 1) {
        assert.ok(major[i].x - major[i - 1].x >= 79.99, `${secondsOnScreen}s`);
      }
    }
  });

  test("the step is a round number of seconds, minutes or hours", () => {
    const ticks = rulerTicks({ scroll: 0, zoom: (10 * RATE) / 1000, width: 1000, rate: RATE });
    const major = ticks.filter((t) => t.label !== null);
    const step = (major[1].frame - major[0].frame) / RATE;
    assert.ok([1, 2, 5].includes(step), String(step));
  });

  test("ticks cover the visible range and carry their frame and x", () => {
    const scroll = 3 * RATE;
    const ticks = rulerTicks({ scroll, zoom: 96, width: 1000, rate: RATE });
    assert.ok(ticks[0].x <= 0 + 80);
    for (const tick of ticks) {
      assert.equal(tick.x, (tick.frame - scroll) / 96);
      assert.ok(tick.x >= -1 && tick.x <= 1001);
    }
  });

  test("a label is whole seconds when the step is, and has decimals when it is not", () => {
    const wide = rulerTicks({ scroll: 0, zoom: (60 * RATE) / 1000, width: 1000, rate: RATE });
    assert.equal(wide.find((t) => t.label !== null && t.frame > 0).label.includes("."), false);
    const close = rulerTicks({ scroll: 0, zoom: (0.5 * RATE) / 1000, width: 1000, rate: RATE });
    assert.equal(close.find((t) => t.label !== null && t.frame > 0).label.includes("."), true);
  });
});
