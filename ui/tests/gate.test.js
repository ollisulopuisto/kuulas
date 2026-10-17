import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  flatBar,
  GATE_OPEN_COMMAND,
  gateAt,
  gateLabelFits,
  gatePixelRuns,
  openStretchEdit,
  stretchAt,
} from "../gate.js";

describe("gatePixelRuns", () => {
  test("clips to the visible frames and returns pixel pairs", () => {
    // zoom 10 frames per pixel, scroll 100, width 50 px: frames 100..600
    const runs = gatePixelRuns(
      [
        [0, 50],
        [90, 200],
        [400, 1000],
        [5000, 6000],
      ],
      100,
      10,
      50,
    );
    assert.deepEqual(runs, [0, 10, 30, 50]);
  });

  test("merges ranges closer than one pixel", () => {
    // 100 frames per pixel; gap of 50 frames = half a pixel
    const runs = gatePixelRuns(
      [
        [1000, 2000],
        [2050, 3000],
        [3300, 4000],
      ],
      0,
      100,
      200,
    );
    assert.deepEqual(runs, [10, 30, 33, 40]);
  });

  test("a range narrower than a pixel still draws one pixel", () => {
    assert.deepEqual(gatePixelRuns([[1005, 1010]], 0, 100, 200), [10, 11]);
  });

  test("thousands of ranges at low zoom collapse to few runs", () => {
    const ranges = [];
    for (let i = 0; i < 5000; i += 1) ranges.push([i * 100, i * 100 + 60]);
    const runs = gatePixelRuns(ranges, 0, 1000, 500);
    assert.equal(runs.length, 2);
    assert.deepEqual(runs, [0, 500]);
  });

  test("reuses the output array and is empty for no gate", () => {
    const out = [9, 9, 9];
    assert.equal(gatePixelRuns([[0, 100]], 0, 1, 200, out), out);
    assert.deepEqual(out, [0, 100]);
    assert.deepEqual(gatePixelRuns([], 0, 1, 200), []);
    assert.deepEqual(gatePixelRuns(undefined, 0, 1, 200), []);
  });
});

describe("gateAt", () => {
  const ranges = [
    [1000, 2000],
    [3000, 3010],
    [5000, 9000],
  ];
  test("finds the range under a frame; the end is exclusive", () => {
    assert.equal(gateAt(ranges, 1500, 10), 0);
    assert.equal(gateAt(ranges, 1000, 10), 0);
    assert.equal(gateAt(ranges, 2000, 10), -1);
    assert.equal(gateAt(ranges, 7000, 10), 2);
    assert.equal(gateAt(ranges, 10, 10), -1);
    assert.equal(gateAt([], 10, 10), -1);
  });
  test("a sliver is still hittable (at least 4 px wide)", () => {
    assert.equal(gateAt(ranges, 3005, 10), 1);
    assert.equal(gateAt(ranges, 3020, 10), 1);
    assert.equal(gateAt(ranges, 3100, 10), -1);
  });
});

describe("gateLabelFits", () => {
  test("needs the text plus padding on both sides", () => {
    assert.equal(gateLabelFits(100, 60), true);
    assert.equal(gateLabelFits(70, 60), false);
    assert.equal(gateLabelFits(0, 60), false);
  });
});

describe("flatBar", () => {
  test("a 1 px floor line: at the bottom for half, on the centre for full", () => {
    assert.deepEqual(flatBar("half", 40), [39, 40]);
    assert.deepEqual(flatBar("full", 40), [19.5, 20.5]);
  });
});

describe("open this stretch", () => {
  test("is one remove_gate_range edit for the whole range", () => {
    assert.equal(GATE_OPEN_COMMAND, "gate.open_stretch");
    assert.deepEqual(openStretchEdit("t1", [1000, 2000]), {
      op: "remove_gate_range",
      args: { track_id: "t1", start: 1000, end: 2000 },
    });
  });
});

describe("stretchAt", () => {
  const project = { tracks: [{ id: "t1", gate: [[100, 200]] }, { id: "t2" }] };
  test("the gate range on a track at a frame, for the keyboard command", () => {
    assert.deepEqual(stretchAt(project, "t1", 150), { trackId: "t1", index: 0, range: [100, 200] });
    assert.equal(stretchAt(project, "t1", 250), null);
    assert.equal(stretchAt(project, "t2", 150), null);
    assert.equal(stretchAt(project, "nope", 150), null);
    assert.equal(stretchAt(project, null, 150), null);
  });
});
