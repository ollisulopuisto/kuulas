// Show log while the automixer runs: the pure parts of the live log viewer.
import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  LIVE_MAX_LINES,
  liveStatusKey,
  mergeLive,
  shouldPoll,
  stickToBottom,
} from "../automix-live-model.js";

const view = (lines = [], started = "t1") => ({ lines, started });

describe("mergeLive", () => {
  test("the first poll fills an empty view", () => {
    const r = mergeLive(view(), { lines: ["a", "b"], started: "t1" });
    assert.deepEqual(r, { reset: false, add: ["a", "b"] });
  });

  test("a later poll adds only the new lines", () => {
    const r = mergeLive(view(["a", "b"]), { lines: ["a", "b", "c", "d"], started: "t1" });
    assert.deepEqual(r, { reset: false, add: ["c", "d"] });
  });

  test("nothing new adds nothing", () => {
    const r = mergeLive(view(["a"]), { lines: ["a"], started: "t1" });
    assert.deepEqual(r, { reset: false, add: [] });
  });

  test("a snapshot that dropped its oldest lines still appends", () => {
    const r = mergeLive(view(["a", "b", "c"]), { lines: ["b", "c", "d"], started: "t1" });
    assert.deepEqual(r, { reset: false, add: ["d"] });
  });

  test("repeated lines are not mistaken for new ones", () => {
    const r = mergeLive(view(["x", "x"]), { lines: ["x", "x", "x"], started: "t1" });
    assert.deepEqual(r, { reset: false, add: ["x"] });
  });

  test("a new run (other start time) replaces the view", () => {
    const r = mergeLive(view(["a", "b"], "t1"), { lines: ["z"], started: "t2" });
    assert.deepEqual(r, { reset: true, add: ["z"] });
  });

  test("lines that do not continue the view replace it", () => {
    const r = mergeLive(view(["a", "b"]), { lines: ["q", "r"], started: "t1" });
    assert.deepEqual(r, { reset: true, add: ["q", "r"] });
  });

  test("an empty answer after lines were shown clears the view", () => {
    const r = mergeLive(view(["a"]), { lines: [], started: "t1" });
    assert.deepEqual(r, { reset: true, add: [] });
  });

  test("at most LIVE_MAX_LINES are added at once", () => {
    const lines = Array.from({ length: LIVE_MAX_LINES + 50 }, (_, i) => `l${i}`);
    const r = mergeLive(view(), { lines, started: "t1" });
    assert.equal(r.add.length, LIVE_MAX_LINES);
    assert.equal(r.add.at(-1), `l${LIVE_MAX_LINES + 49}`);
  });
});

describe("stickToBottom", () => {
  test("at the bottom follows", () => {
    assert.equal(stickToBottom({ scrollTop: 600, clientHeight: 400, scrollHeight: 1000 }), true);
  });
  test("a few pixels short still follows", () => {
    assert.equal(stickToBottom({ scrollTop: 590, clientHeight: 400, scrollHeight: 1000 }), true);
  });
  test("scrolled up stays put", () => {
    assert.equal(stickToBottom({ scrollTop: 100, clientHeight: 400, scrollHeight: 1000 }), false);
  });
  test("a short log with no scrolling follows", () => {
    assert.equal(stickToBottom({ scrollTop: 0, clientHeight: 400, scrollHeight: 300 }), true);
  });
});

describe("shouldPoll and the status", () => {
  test("polls only while open and running", () => {
    assert.equal(shouldPoll({ open: true, running: true }), true);
    assert.equal(shouldPoll({ open: false, running: true }), false);
    assert.equal(shouldPoll({ open: true, running: false }), false);
  });
  test("the label says Running or Finished", () => {
    assert.equal(liveStatusKey(true), "ui.automix.live_running");
    assert.equal(liveStatusKey(false), "ui.automix.live_finished");
  });
});
