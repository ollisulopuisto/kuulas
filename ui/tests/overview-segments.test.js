import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  audibleSegments,
  overviewCandidateTicks,
  overviewMarks,
  overviewRuns,
} from "../overview-segments.js";

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

describe("overviewCandidateTicks", () => {
  test("maps open candidate spans to ticks, clipping spans to the timeline", () => {
    const ticks = overviewCandidateTicks(
      [
        { id: "before", state: "open", spans: [[-20, 20]] },
        { id: "inside", state: "open", spans: [[250, 260]] },
        { id: "after", state: "open", spans: [[990, 1020]] },
        { id: "closed", state: "kept", spans: [[500, 600]] },
      ],
      1000,
      100,
    );
    assert.deepEqual(ticks, [
      { id: "before", x: 0 },
      { id: "inside", x: 25 },
      { id: "after", x: 99 },
    ]);
  });

  test("tiny spans and multiple audio spans each get one stable tick", () => {
    assert.deepEqual(
      overviewCandidateTicks(
        [
          {
            id: "split",
            state: "open",
            spans: [
              [40, 41],
              [600, 800],
            ],
          },
        ],
        1000,
        100,
      ),
      [
        { id: "split", x: 4 },
        { id: "split", x: 60 },
      ],
    );
  });
});

describe("overviewMarks", () => {
  test("uses round five-minute marks for the owner's 25-minute overview", () => {
    const marks = overviewMarks(25 * 60 * 48000, 1000, 48000, String);
    assert.deepEqual(marks, [
      { x: 200, label: "300" },
      { x: 400, label: "600" },
      { x: 600, label: "900" },
      { x: 800, label: "1200" },
    ]);
  });

  test("chooses the smallest round scale that keeps at most four interior marks", () => {
    for (const [minutes, step] of [
      [4.5, 1],
      [25, 5],
      [45, 10],
      [65, 15],
      [85, 20],
      [125, 30],
      [245, 60],
    ]) {
      const marks = overviewMarks(minutes * 60, 1000, 1, String);
      assert.ok(marks.length <= 4);
      assert.equal(Number(marks[0].label), step * 60);
      assert.ok(marks.every((mark) => Number(mark.label) % (step * 60) === 0));
    }
  });

  test("short edits use seconds and long edits still have at most four marks", () => {
    assert.deepEqual(overviewMarks(96000, 400, 48000, String), [{ x: 200, label: "1" }]);
    assert.ok(overviewMarks(12 * 3600, 1000, 1, String).length <= 4);
  });

  test("empty strips have no marks and narrow strips avoid crowding", () => {
    assert.deepEqual(overviewMarks(0, 400, 48000, String), []);
    assert.deepEqual(overviewMarks(100, 0, 1, String), []);
    assert.ok(overviewMarks(1500, 100, 1, String).length <= 1);
  });
});
