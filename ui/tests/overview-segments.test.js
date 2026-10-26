import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { audibleSegments, overviewMarks, overviewRuns } from "../overview-segments.js";

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

describe("overviewMarks", () => {
  // Owner, 2026-10-25: the strip gets its own times, sparse, at a quarter, half and three quarters
  // of the edit (no times at the two ends).
  test("marks a quarter, half and three quarters of the edit, not the ends", () => {
    const marks = overviewMarks(4000, 400, 1, (seconds) => `t${seconds}`);
    assert.deepEqual(marks, [
      { x: 100, label: "t1000" },
      { x: 200, label: "t2000" },
      { x: 300, label: "t3000" },
    ]);
  });

  test("the times come from the project rate, not from frames", () => {
    const marks = overviewMarks(96000, 100, 48000, (seconds) => String(seconds));
    assert.deepEqual(
      marks.map((mark) => mark.label),
      ["0.5", "1", "1.5"],
    );
  });
});
