import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { implicitSilenceRanges } from "../clip-silence.js";
import { mutePlan } from "../edit-plans.js";

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

test("the opening between closed stretches is also an implicit portion", () => {
  const project = {
    tracks: [
      {
        id: "t",
        clips: [
          {
            id: "c",
            start: 0,
            offset: 0,
            length: 1000,
            auto_silence: [
              [100, 200],
              [500, 600],
            ],
          },
        ],
      },
    ],
  };
  const hit = (x) =>
    hitTest({
      layout: { rows: [{ kind: "track", id: "t", index: 0, top: 0, height: 48 }] },
      project,
      view: { scroll: 0, zoom: 10, scrollY: 0, showGates: true },
      x,
      y: RULER_HEIGHT + 10,
    });
  assert.deepEqual(hit(35).gate?.range, [200, 500]);
  assert.equal(hit(35).gate?.closed, false);
  assert.equal(hit(35).gate?.clipId, "c");
  assert.deepEqual(hit(21).implicitRange, [200, 500]);
  assert.equal(hit(21).edge, "start");
});

test("the reported 4:08.967 click and M target the opening, with source offsets", () => {
  const S = 48000;
  const start = Math.round(238.348 * S);
  const offset = 1000 * S;
  const at = Math.round(248.967 * S);
  for (const legacy of [false, true]) {
    const a = 248.6 * S;
    const b = 249.7 * S;
    const gate = [
      [start, a],
      [b, start + 150.184 * S],
    ];
    const clip = {
      id: "parent",
      media: "m",
      start,
      offset,
      length: Math.round(150.184 * S),
      auto_silence: legacy ? [] : gate.map(([a, b]) => [offset + a - start, offset + b - start]),
    };
    const project = { tracks: [{ id: "track1", gate: legacy ? gate : [], clips: [clip] }] };
    const hit = hitTest({
      project,
      layout: { rows: [{ kind: "track", id: "track1", index: 0, top: 0, height: 240 }] },
      view: { scroll: 248 * S, zoom: 480, scrollY: 0, showGates: true },
      x: (at - 248 * S) / 480,
      y: RULER_HEIGHT + 180,
    });
    assert.equal(hit.gate.closed, false);
    assert.deepEqual(hit.gate.range, [a, b]);
    const change = mutePlan({
      project,
      selection: new Set(["parent"]),
      playhead: at,
      implicitRangeTarget: hit.gate,
    });
    assert.equal(change.op, "open_gated_region");
    assert.equal(change.args.clip_id, "parent");
    assert.equal(change.args.muted, true);
  }
});
