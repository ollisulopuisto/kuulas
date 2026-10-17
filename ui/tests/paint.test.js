import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { makeWaveformJob, paintWaveforms } from "../paint.js";
import { TILE_PEAKS } from "../waveform.js";

function fakeContext() {
  const calls = [];
  const sets = [];
  const target = {};
  return {
    calls,
    sets,
    ctx: new Proxy(target, {
      get:
        (_t, name) =>
        (...args) =>
          calls.push([name, ...args]),
      set: (_t, name, value) => {
        sets.push([name, value]);
        return true;
      },
    }),
  };
}

const palette = [{ fill: "#123", ink: "#fff", wave: "#456" }];
const job = (over = {}) => ({
  id: 1,
  width: 200,
  height: 100,
  ratio: 2,
  scroll: 0,
  zoom: 256,
  scrollY: 0,
  rulerHeight: 24,
  mode: "half",
  scale: "linear",
  gain: 1,
  palette,
  rows: [
    {
      top: 0,
      height: 48,
      paletteIndex: 0,
      clips: [{ id: "c1", media: "m1", start: 0, offset: 0, length: 100 * 256, muted: false }],
    },
  ],
  ...over,
});
const loud = () => {
  const tile = new Float32Array(TILE_PEAKS * 2);
  for (let i = 0; i < TILE_PEAKS; i += 1) {
    tile[2 * i] = -0.5;
    tile[2 * i + 1] = 0.5;
  }
  return tile;
};
const count = (calls, name) => calls.filter((c) => c[0] === name).length;
// One-pixel-wide rects are the bars; the other rect is the clip region.
const bars = (calls) => calls.filter((c) => c[0] === "rect" && c[3] === 1).length;

describe("painting waveforms (what the worker runs)", () => {
  test("a clip is a body plus one bar per pixel column, drawn from the tile", () => {
    const { ctx, calls } = fakeContext();
    const out = paintWaveforms(ctx, job(), () => loud());
    assert.deepEqual(out.missing, []);
    assert.equal(count(calls, "fillRect"), 1, "the clip body");
    assert.equal(bars(calls), 100, "100 px wide at 256 frames per pixel");
    assert.ok(count(calls, "fill") >= 1);
  });

  test("a tile that has not arrived is reported once, and its columns stay empty", () => {
    const { ctx, calls } = fakeContext();
    const asked = [];
    const out = paintWaveforms(ctx, job(), (media, level, tile) => {
      asked.push([media, level, tile]);
      return undefined;
    });
    assert.deepEqual(out.missing, [{ media: "m1", level: 256, tile: 0 }]);
    assert.equal(bars(calls), 0);
    assert.ok(asked.length > 0);
  });

  test("rows and clips outside the view are skipped (no tile is asked for)", () => {
    const { ctx, calls } = fakeContext();
    const far = job({
      scroll: 10_000_000,
      rows: [
        {
          top: 0,
          height: 48,
          paletteIndex: 0,
          clips: [{ id: "c", media: "m", start: 0, offset: 0, length: 5000, muted: false }],
        },
        {
          top: 5000,
          height: 48,
          paletteIndex: 0,
          clips: [
            { id: "d", media: "m", start: 10_000_000, offset: 0, length: 5000, muted: false },
          ],
        },
      ],
    });
    const out = paintWaveforms(ctx, far, () => {
      throw new Error("asked for a tile that is not on screen");
    });
    assert.deepEqual(out.missing, []);
    assert.equal(count(calls, "fillRect"), 0);
  });

  test("a muted clip is drawn faint, then the alpha is put back", () => {
    const { ctx, sets } = fakeContext();
    const muted = job();
    muted.rows[0].clips[0].muted = true;
    paintWaveforms(ctx, muted, () => loud());
    const alphas = sets.filter((s) => s[0] === "globalAlpha").map((s) => s[1]);
    assert.ok(alphas.includes(0.35));
    assert.equal(alphas.at(-1), 1);
  });

  test("the canvas is scaled for the device and cleared first", () => {
    const { ctx, calls } = fakeContext();
    paintWaveforms(ctx, job(), () => loud());
    assert.deepEqual(calls[0], ["setTransform", 2, 0, 0, 2, 0, 0]);
    assert.equal(calls[1][0], "clearRect");
  });

  test("makeWaveformJob keeps only what is on screen, as plain data", () => {
    const project = {
      buses: [],
      tracks: [
        {
          id: "t1",
          kind: "speech",
          clips: [
            { id: "c1", media: "m", start: 0, offset: 0, length: 1000, muted: false, gain_db: 0 },
          ],
        },
        { id: "t2", kind: "music", clips: [] },
      ],
    };
    const state = {
      project,
      scroll: 0,
      zoom: 10,
      scrollY: 0,
      laneHeight: 48,
      waveformMode: "half",
      waveformScale: "linear",
      waveformGain: 1,
    };
    const made = makeWaveformJob(state, { width: 400, height: 300, ratio: 1, id: 7 }, palette);
    assert.equal(made.id, 7);
    assert.equal(made.rows.length, 2);
    assert.deepEqual(Object.keys(made.rows[0].clips[0]).sort(), [
      "id",
      "length",
      "media",
      "muted",
      "offset",
      "start",
    ]);
    assert.doesNotThrow(() => structuredClone(made));
  });
});
