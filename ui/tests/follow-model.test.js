import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  arrowOf,
  followStep,
  HANDLE_PX,
  JUMP_SOURCES,
  onHandle,
  sourceEvent,
} from "../follow-model.js";

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

describe("which user actions jump (owner, 2026-10-21)", () => {
  const explicit = [
    "nav.start",
    "nav.end",
    "nav.in",
    "nav.out",
    "nav.to_resume",
    "marker.next",
    "marker.previous",
    "markers-panel.row",
    "markers-panel.clip",
    "go-to-time",
    "transcript.word-click",
    "transcript.pause-click",
    "transcript.find-hit",
    "tab-stop",
    "sync.drift-step",
    "candidate.select",
    "inspector.source-row",
  ];
  const minor = [
    "nudge",
    "ruler-click",
    "lane-click",
    "scrub",
    "transcript.cursor-keys",
    "edit.splice-cursor",
    "context-menu-press",
    "open-project",
  ];

  test("every explicit jump re-engages Follow and shows the target", () => {
    for (const source of explicit) {
      assert.equal(JUMP_SOURCES[source], "jump", source);
      assert.deepEqual(followStep(off, sourceEvent(source, { inView: false })), {
        follow: true,
        shouldScroll: true,
      });
    }
  });

  test("minor adjustments stay plain seeks: Follow stays off, the view stays put", () => {
    for (const source of minor) {
      assert.equal(JUMP_SOURCES[source], "seek", source);
      assert.deepEqual(followStep(off, sourceEvent(source, { inView: false })), {
        follow: false,
        shouldScroll: false,
      });
    }
  });

  test("the table lists exactly these actions", () => {
    assert.deepEqual(Object.keys(JUMP_SOURCES).sort(), [...explicit, ...minor].sort());
  });

  test("an unknown source is a plain seek (fails closed)", () => {
    assert.equal(sourceEvent("nope", { inView: true }).type, "seek");
  });
});
