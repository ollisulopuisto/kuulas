import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { arrowOf, followStep, HANDLE_PX, onHandle } from "../follow-model.js";

const on = { follow: true };
const off = { follow: false };

describe("follow is a state, not an action", () => {
  test("a view operation while playing detaches", () => {
    assert.deepEqual(followStep(on, { type: "view-op", playing: true }), {
      follow: false,
      shouldScroll: false,
    });
  });

  test("a view operation while stopped leaves follow on (nothing to follow)", () => {
    assert.equal(followStep(on, { type: "view-op", playing: false }).follow, true);
  });

  test("starting and stopping playback reset follow to on", () => {
    assert.equal(followStep(off, { type: "play-start" }).follow, true);
    assert.equal(followStep(off, { type: "play-stop" }).follow, true);
  });

  test("a transport jump re-engages and scrolls only when the target is off screen", () => {
    assert.deepEqual(followStep(off, { type: "jump", inView: false }), {
      follow: true,
      shouldScroll: true,
    });
    assert.deepEqual(followStep(off, { type: "jump", inView: true }), {
      follow: true,
      shouldScroll: false,
    });
  });

  test("clicking the playhead handle re-engages without scrolling", () => {
    assert.deepEqual(followStep(off, { type: "handle" }), { follow: true, shouldScroll: false });
  });

  test("Show the playhead (chip, arrow, menu) re-engages and scrolls to it", () => {
    assert.deepEqual(followStep(off, { type: "show", inView: false }), {
      follow: true,
      shouldScroll: true,
    });
    assert.equal(followStep(off, { type: "show", inView: true }).shouldScroll, false);
  });

  test("the chip toggles: on detaches, off shows the playhead", () => {
    assert.equal(followStep(on, { type: "toggle", inView: true }).follow, false);
    assert.deepEqual(followStep(off, { type: "toggle", inView: false }), {
      follow: true,
      shouldScroll: true,
    });
  });

  test("a seek outside the view scrolls once with follow on, never with it off", () => {
    assert.equal(followStep(on, { type: "seek", inView: false }).shouldScroll, true);
    assert.equal(followStep(on, { type: "seek", inView: true }).shouldScroll, false);
    assert.deepEqual(followStep(off, { type: "seek", inView: false }), {
      follow: false,
      shouldScroll: false,
    });
  });

  test("nothing implicit re-engages: the playhead entering view, a tick, a click near the time", () => {
    for (const type of ["playhead-in-view", "tick", "timer", "click-near-time"]) {
      assert.deepEqual(followStep(off, { type, inView: true }), {
        follow: false,
        shouldScroll: false,
      });
    }
  });
});

describe("the playhead handle hit area", () => {
  test("is about 6 px either side", () => {
    assert.equal(HANDLE_PX, 6);
    assert.equal(onHandle({ playhead: 1000, frame: 1060, zoom: 10 }), true);
    assert.equal(onHandle({ playhead: 1000, frame: 940, zoom: 10 }), true);
    assert.equal(onHandle({ playhead: 1000, frame: 1061, zoom: 10 }), false);
  });
});

describe("the edge arrow", () => {
  const view = { scroll: 1000, zoom: 10, width: 100 }; // frames 1000..2000
  test("shows only with follow off and the playhead out of view", () => {
    assert.equal(arrowOf({ ...view, follow: true, playhead: 5000 }), null);
    assert.equal(arrowOf({ ...view, follow: false, playhead: 1500 }), null);
  });
  test("points toward the playhead", () => {
    assert.equal(arrowOf({ ...view, follow: false, playhead: 5000 }), "right");
    assert.equal(arrowOf({ ...view, follow: false, playhead: 10 }), "left");
  });
});
