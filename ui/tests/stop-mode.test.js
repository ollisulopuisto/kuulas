import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  createStopGesture,
  DEFAULT_STOP_MODE,
  nextStopMode,
  STOP_MODES,
  stopModeChoice,
} from "../stop-mode.js";

describe("the preference", () => {
  test("two steps is the default; anything unknown falls back to it", () => {
    assert.equal(DEFAULT_STOP_MODE, "two_step");
    assert.equal(stopModeChoice(null), "two_step");
    assert.equal(stopModeChoice("nonsense"), "two_step");
    assert.equal(stopModeChoice("hold"), "hold");
  });
  test("the menu item cycles through the three", () => {
    assert.deepEqual(STOP_MODES, ["two_step", "one_click", "hold"]);
    assert.equal(nextStopMode("two_step"), "one_click");
    assert.equal(nextStopMode("one_click"), "hold");
    assert.equal(nextStopMode("hold"), "two_step");
    assert.equal(nextStopMode("bad"), "one_click");
  });
});

describe("two steps", () => {
  test("the first press only asks; the recording goes on", () => {
    const g = createStopGesture();
    const v = g.press(1000);
    assert.equal(v.state, "confirming");
    assert.equal(v.stopped, false);
    assert.equal(v.secondsLeft, 4);
  });
  test("a second press within the window stops, once", () => {
    const g = createStopGesture();
    g.press(1000);
    g.release(1100);
    const v = g.press(4000);
    assert.equal(v.state, "stopped");
    assert.equal(v.stopped, true);
    g.release(4100);
    const again = g.press(4200);
    assert.equal(again.stopped, false);
    assert.equal(again.state, "stopped");
  });
  test("the window running out returns quietly to recording", () => {
    const g = createStopGesture({ confirmMs: 4000 });
    g.press(1000);
    g.release(1050);
    assert.equal(g.tick(4999).state, "confirming");
    assert.equal(g.tick(4999).secondsLeft, 1);
    const v = g.tick(5001);
    assert.equal(v.state, "recording");
    assert.equal(v.stopped, false);
    // and a press after that starts over: it asks again, it does not stop
    assert.equal(g.press(5100).state, "confirming");
  });
  test("a press after the window (no tick in between) asks again rather than stops", () => {
    const g = createStopGesture({ confirmMs: 4000 });
    g.press(1000);
    g.release(1050);
    const v = g.press(9000);
    assert.equal(v.state, "confirming");
    assert.equal(v.stopped, false);
  });
  test("a key held down (auto-repeat) is one press, not two", () => {
    const g = createStopGesture();
    g.press(1000);
    const v = g.press(1030);
    assert.equal(v.state, "confirming");
    assert.equal(v.stopped, false);
  });
  test("time going backwards never stops and never leaves it stuck", () => {
    const g = createStopGesture({ confirmMs: 4000 });
    g.press(10_000);
    g.release(10_050);
    const back = g.tick(5000);
    assert.equal(back.state, "confirming");
    assert.equal(back.stopped, false);
    // the window counts from the clock's new place, so it still ends
    assert.equal(g.tick(9001).state, "recording");
  });
  test("a press while time ran backwards is no stop either", () => {
    const g = createStopGesture({ confirmMs: 4000 });
    g.press(10_000);
    g.release(10_050);
    const v = g.press(2000);
    assert.equal(v.stopped, false);
    assert.equal(v.state, "confirming");
  });
  test("reset goes back to recording", () => {
    const g = createStopGesture();
    g.press(0);
    g.reset();
    assert.equal(g.tick(10).state, "recording");
  });
});

describe("one click", () => {
  test("the first press stops", () => {
    const g = createStopGesture({ mode: "one_click" });
    const v = g.press(1000);
    assert.equal(v.state, "stopped");
    assert.equal(v.stopped, true);
  });
});

describe("hold 2 s", () => {
  test("delegates to the hold: a short hold does nothing", () => {
    const g = createStopGesture({ mode: "hold" });
    g.press(1000);
    assert.equal(g.tick(2000).progress, 0.5);
    assert.equal(g.tick(2000).state, "holding");
    g.release(2500);
    const v = g.tick(3500);
    assert.equal(v.state, "recording");
    assert.equal(v.stopped, false);
  });
  test("a full hold stops and reports how long it was held", () => {
    const g = createStopGesture({ mode: "hold", holdMs: 2000 });
    g.press(1000);
    const v = g.tick(3000);
    assert.equal(v.stopped, true);
    assert.equal(v.state, "stopped");
    assert.equal(v.heldMs, 2000);
  });
  test("a fresh press after an early release starts the hold over", () => {
    const g = createStopGesture({ mode: "hold" });
    g.press(1000);
    g.release(2900);
    g.press(3000);
    assert.equal(g.tick(4000).stopped, false);
    assert.equal(g.tick(5000).stopped, true);
  });
});

test("an unknown mode behaves as the default", () => {
  const g = createStopGesture({ mode: "weird" });
  assert.equal(g.mode, "two_step");
  assert.equal(g.press(0).state, "confirming");
});
