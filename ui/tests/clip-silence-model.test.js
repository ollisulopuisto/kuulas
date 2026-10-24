import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { implicitSilenceRanges } from "../clip-silence.js";

describe("implicit clip silence", () => {
  test("source-frame ranges map to this clip's timeline position", () => {
    assert.deepEqual(
      implicitSilenceRanges({ start: 500, offset: 40, length: 100, auto_silence: [[50, 80]] }),
      [[510, 540]],
    );
  });

  test("only overlap with the clip is shown", () => {
    assert.deepEqual(
      implicitSilenceRanges({ start: 500, offset: 40, length: 20, auto_silence: [[0, 100]] }),
      [[500, 520]],
    );
  });
});

import { hitTest, RULER_HEIGHT } from "../lanes.js";

test("an implicit silence boundary is an editable edge, not just a track gate", () => {
  const project = {
    tracks: [
      {
        id: "t",
        gate: [],
        clips: [{ id: "c", start: 0, offset: 0, length: 1000, auto_silence: [[100, 200]] }],
      },
    ],
  };
  const hit = hitTest({
    layout: { rows: [{ kind: "track", id: "t", index: 0, top: 0, height: 48 }] },
    project,
    view: { scroll: 0, zoom: 10, scrollY: 0, showGates: true },
    x: 10,
    y: RULER_HEIGHT + 10,
  });
  assert.equal(hit.clip.id, "c");
  assert.equal(hit.edge, "start");
  assert.deepEqual(hit.implicitRange, [100, 200]);
});

test("implicit silence borders at the parent clip edges remain editable and target that clip", () => {
  for (const [range, x, edge] of [
    [[0, 200], 0, "start"],
    [[800, 1000], 100, "end"],
  ]) {
    const project = {
      tracks: [
        {
          id: "t",
          gate: [],
          clips: [{ id: "c", start: 0, offset: 0, length: 1000, auto_silence: [range] }],
        },
      ],
    };
    const hit = hitTest({
      layout: { rows: [{ kind: "track", id: "t", index: 0, top: 0, height: 48 }] },
      project,
      view: { scroll: 0, zoom: 10, scrollY: 0, showGates: true },
      x,
      y: RULER_HEIGHT + 10,
    });
    assert.equal(hit.edge, edge);
    assert.deepEqual(hit.implicitRange, range);
    assert.equal(hit.gate?.clipId, "c");
  }
});

test("implicit silence hit testing keeps the topmost overlapping clip identity", () => {
  const project = {
    tracks: [
      {
        id: "t",
        gate: [],
        clips: [
          { id: "a", start: 0, offset: 0, length: 1000, auto_silence: [[100, 300]] },
          { id: "b", start: 0, offset: 0, length: 1000, auto_silence: [[200, 400]] },
        ],
      },
    ],
  };
  const hit = hitTest({
    layout: { rows: [{ kind: "track", id: "t", index: 0, top: 0, height: 48 }] },
    project,
    view: { scroll: 0, zoom: 10, scrollY: 0, showGates: true },
    x: 25,
    y: RULER_HEIGHT + 10,
  });
  assert.equal(hit.clip.id, "b");
  assert.equal(hit.gate?.clipId, "b");
  assert.deepEqual(hit.gate?.range, [200, 400]);
});
