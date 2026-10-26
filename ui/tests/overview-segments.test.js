import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { audibleSegments, overviewRuns } from "../overview-segments.js";

const clip = (start, length, extra = {}) => ({ id: `c${start}`, start, length, ...extra });

describe("audibleSegments", () => {
  test("clips merge, gaps between clips stay", () => {
    const track = { clips: [clip(100, 100), clip(0, 100), clip(300, 50)] };
    assert.deepEqual(audibleSegments(track), [
      [0, 200],
      [300, 350],
    ]);
  });
  test("a muted clip and a muted track are gaps", () => {
    assert.deepEqual(audibleSegments({ clips: [clip(0, 100, { muted: true }), clip(100, 50)] }), [
      [100, 150],
    ]);
    assert.deepEqual(audibleSegments({ mute: true, clips: [clip(0, 100)] }), []);
  });
  test("gate ranges are cut out, except under a clip that keeps the mic open", () => {
    const track = { gate: [[40, 60]], clips: [clip(0, 100)] };
    assert.deepEqual(audibleSegments(track), [
      [0, 40],
      [60, 100],
    ]);
    const open = { gate: [[40, 60]], clips: [clip(0, 100, { ungated: true })] };
    assert.deepEqual(audibleSegments(open), [[0, 100]]);
  });
  test("clip Auto-Silence is mapped from source frames into the overview", () => {
    const track = {
      clips: [clip(100, 100, { offset: 500, auto_silence: [[520, 540]] })],
    };
    assert.deepEqual(audibleSegments(track), [
      [100, 120],
      [140, 200],
    ]);
  });
  test("one clip's Auto-Silence does not hide overlapping audio on the same track", () => {
    const track = {
      clips: [clip(100, 100, { auto_silence: [[120, 140]] }), clip(100, 100, { id: "overlap" })],
    };
    assert.deepEqual(audibleSegments(track), [[100, 200]]);
  });
  test("preview ranges are cut out too", () => {
    const track = { gate: [[0, 10]], clips: [clip(0, 100)] };
    assert.deepEqual(audibleSegments(track, [[50, 100]]), [[10, 50]]);
  });
});

describe("overviewRuns", () => {
  test("pixels, minimum one pixel wide, gaps under a pixel merge", () => {
    // 1000 frames over 100 px: 10 frames per pixel
    const runs = overviewRuns(
      [
        [0, 2],
        [5, 100],
        [300, 400],
      ],
      1000,
      100,
    );
    assert.deepEqual(runs, [0, 10, 30, 40]);
  });
  test("short speech still shows", () => {
    assert.deepEqual(overviewRuns([[500, 501]], 1000, 100), [50, 51]);
  });
});
