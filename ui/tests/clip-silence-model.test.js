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
