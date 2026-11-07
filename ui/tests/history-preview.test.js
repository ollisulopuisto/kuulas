import assert from "node:assert/strict";
import { test } from "node:test";
import { drawHistoryPreview, historyPreviewBoxes } from "../history-preview.js";
import { RULER_HEIGHT } from "../lanes.js";

test("history previews use visible track rows and clip geometry to the viewport", () => {
  const clips = [
    { track: "A", clip: "a", start: 5, end: 15 },
    { track: "B", clip: "b", start: 18, end: 25 },
    { track: "C", clip: "c", start: 10, end: 20 },
    { track: "missing", clip: "d", start: 10, end: 20 },
    { track: "A", start: 10, end: 20 },
    { track: "A", clip: "e", start: -20, end: -1 },
  ];
  const layout = {
    rows: [
      { kind: "track", id: "A", top: 0, height: 40 },
      { kind: "gap", id: "gap", top: 40, height: 10 },
      { kind: "track", id: "B", top: 50, height: 40 },
      { kind: "track", id: "C", top: 90, height: 40 },
    ],
  };
  const boxes = historyPreviewBoxes(clips, {
    layout,
    view: { scroll: 10, zoom: 2, scrollY: 15, width: 10, height: 70 },
  });
  assert.deepEqual(boxes, [
    { clipId: "a", trackId: "A", x: 0, y: RULER_HEIGHT, w: 2.5, h: 23 },
    { clipId: "b", trackId: "B", x: 4, y: RULER_HEIGHT + 37, w: 3.5, h: 9 },
  ]);
});

test("empty and invalid preview geometry produces no boxes", () => {
  const layout = { rows: [{ kind: "bus", id: "bus", top: 0, height: 40 }] };
  assert.deepEqual(
    historyPreviewBoxes([{ track: "A", start: 1, end: 2 }], {
      layout,
      view: { scroll: 0, zoom: 1, scrollY: 0, width: 10, height: 80 },
    }),
    [],
  );
});

test("historical boxes are drawn as quiet dashed outlines", () => {
  const calls = [];
  const context = {
    save: () => calls.push(["save"]),
    restore: () => calls.push(["restore"]),
    setLineDash: (dash) => calls.push(["dash", dash]),
    strokeRect: (...rect) => calls.push(["rect", ...rect]),
  };
  drawHistoryPreview(context, [{ x: 2, y: 30, w: 16, h: 36 }], "var(--accent)");
  assert.deepEqual(calls, [
    ["save"],
    ["dash", [5, 4]],
    ["rect", 2.5, 30.5, 15, 35],
    ["dash", []],
    ["restore"],
  ]);
});
